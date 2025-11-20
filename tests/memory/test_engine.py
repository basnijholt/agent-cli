"""Unit/integration coverage for the memory engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Self

import pytest

from agent_cli.memory import engine, tasks
from agent_cli.memory.models import ChatRequest, MemoryMetadata, Message, StoredMemory


class _DummyReranker:
    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Return uniform relevance for all pairs."""
        return [1.0 for _ in pairs]


class _RecordingCollection:
    """Minimal Chroma-like collection that keeps everything in memory."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, dict[str, Any]]] = {}

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        for doc_id, doc, meta in zip(ids, documents, metadatas, strict=False):
            self._store[doc_id] = (doc, dict(meta))

    def query(
        self,
        *,
        query_texts: list[str],  # noqa: ARG002
        n_results: int,
        where: dict[str, Any],
    ) -> dict[str, Any]:
        conv = where.get("conversation_id")
        items = [
            (doc_id, doc, meta)
            for doc_id, (doc, meta) in self._store.items()
            if meta.get("conversation_id") == conv
        ]
        ids = [doc_id for doc_id, _, _ in items][:n_results]
        docs = [doc for _, doc, _ in items][:n_results]
        metas = [meta for _, _, meta in items][:n_results]
        return {
            "documents": [docs],
            "metadatas": [metas],
            "ids": [ids],
            "distances": [[0.0 for _ in ids]],
        }

    def get(
        self,
        *,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        if where is None:
            return {"documents": [], "metadatas": [], "ids": []}

        def _matches(meta: dict[str, Any], clause: dict[str, Any]) -> bool:
            for key, value in clause.items():
                if isinstance(value, dict) and "$ne" in value and meta.get(key) == value["$ne"]:
                    return False
                if meta.get(key) != value:
                    return False
            return True

        clauses = where.get("$and", [where])  # type: ignore[arg-type]
        results = [
            (doc_id, (doc, meta))
            for doc_id, (doc, meta) in self._store.items()
            if all(_matches(meta, clause) for clause in clauses)
        ]
        docs = [doc for _, (doc, _) in results]
        metas = [meta for _, (_, meta) in results]
        ids = [doc_id for doc_id, _ in results]
        return {"documents": [docs], "metadatas": [metas], "ids": ids}

    def delete(self, ids: list[str] | None = None, where: dict[str, Any] | None = None) -> None:  # noqa: ARG002
        if ids:
            for doc_id in ids:
                self._store.pop(doc_id, None)


class _DummyStreamResponse:
    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def aiter_lines(self) -> Any:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b"error"


class _DummyAsyncClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def stream(self, *_args: Any, **_kwargs: Any) -> _DummyStreamResponse:
        return _DummyStreamResponse(
            [
                'data: {"choices":[{"delta":{"content":"Hello"}}]}',
                'data: {"choices":[{"delta":{"content":" Jane"}}]}',
                "data: [DONE]",
            ],
        )

    async def __aenter__(self) -> Self:  # type: ignore[misc]
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_augment_chat_request_disables_with_zero_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit memory_top_k=0 should skip retrieval and leave request untouched."""
    # Avoid calling external LLM during consolidation.
    engine._consolidate_retrieval_entries = lambda entries, **_: entries  # type: ignore[assignment]
    request = ChatRequest(
        model="x",
        messages=[Message(role="user", content="hello")],
        memory_top_k=0,
    )

    async def fake_rewrite(*_args: Any, **_kwargs: Any) -> list[str]:
        return ["hello"]

    monkeypatch.setattr(engine, "_rewrite_queries", fake_rewrite)
    aug_request, retrieval, conversation_id, summaries = await engine.augment_chat_request(
        request,
        collection=_RecordingCollection(),
        reranker_model=_DummyReranker(),  # type: ignore[arg-type]
        openai_base_url="http://llm",
        api_key=None,
    )

    assert retrieval is None
    assert aug_request.messages[-1].content == "hello"
    assert conversation_id == "default"
    assert summaries == []


@pytest.mark.asyncio
async def test_retrieve_memory_prefers_diversity_and_adds_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    mem_primary = StoredMemory(
        id="1",
        content="We talked about biking routes around town",
        metadata=MemoryMetadata(
            conversation_id="conv1",
            role="memory",
            created_at=now.isoformat(),
            salience=0.5,
            tags=["biking"],
        ),
        distance=0.1,
    )
    mem_similar = StoredMemory(
        id="2",
        content="More biking chat and cycling gear opinions",
        metadata=MemoryMetadata(
            conversation_id="conv1",
            role="memory",
            created_at=now.isoformat(),
            salience=0.2,
            tags=["biking", "gear"],
        ),
        distance=0.2,
    )
    mem_diverse = StoredMemory(
        id="3",
        content="Planning a trip to Japan next spring",
        metadata=MemoryMetadata(
            conversation_id="global",
            role="memory",
            created_at=(now - timedelta(days=1)).isoformat(),
            salience=0.9,
            tags=["travel", "japan"],
        ),
        distance=0.3,
    )

    call_count = 0

    def fake_query_memories(
        _collection: Any,
        *,
        conversation_id: str,
        text: str,  # noqa: ARG001
        n_results: int,  # noqa: ARG001
    ) -> list[StoredMemory]:
        nonlocal call_count
        call_count += 1
        return [mem_primary, mem_similar] if conversation_id == "conv1" else [mem_diverse]

    monkeypatch.setattr(engine, "query_memories", fake_query_memories)
    monkeypatch.setattr(
        engine,
        "predict_relevance",
        lambda _model, pairs: [0.9, 0.1, 0.8][: len(pairs)],
    )
    monkeypatch.setattr(
        engine,
        "get_summary_entry",
        lambda _collection, _cid, role: StoredMemory(  # type: ignore[return-value]
            id=f"{role}-id",
            content=f"{role} content",
            metadata=MemoryMetadata(
                conversation_id="conv1",
                role=role,
                created_at=now.isoformat(),
            ),
        ),
    )

    retrieval, summaries = engine._retrieve_memory(
        collection=_RecordingCollection(),
        conversation_id="conv1",
        queries=["I enjoy biking and also travel planning"],
        top_k=2,
        reranker_model=_DummyReranker(),  # type: ignore[arg-type]
    )

    contents = [entry.content for entry in retrieval.entries]
    assert len(contents) == 2
    assert mem_primary.content in contents
    assert mem_diverse.content in contents  # diverse item beats near-duplicate
    assert any("Short summary" in text for text in summaries)
    assert any("Long summary" in text for text in summaries)
    assert call_count == 2


@pytest.mark.asyncio
async def test_query_rewrite_merges_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multiple rewrites should expand candidate set."""
    call_count = 0

    def fake_query_memories(
        _collection: Any,
        *,
        conversation_id: str,
        text: str,
        n_results: int,  # noqa: ARG001
    ) -> list[StoredMemory]:
        nonlocal call_count
        call_count += 1
        return [
            StoredMemory(
                id=f"{conversation_id}-{text}",
                content=f"{text} content",
                metadata=MemoryMetadata(
                    conversation_id=conversation_id,
                    role="memory",
                    created_at=datetime.now(UTC).isoformat(),
                ),
            ),
        ]

    monkeypatch.setattr(engine, "query_memories", fake_query_memories)

    async def fake_rewrite_queries(*_args: Any, **_kwargs: Any) -> list[str]:
        return ["q1", "q2"]

    monkeypatch.setattr(engine, "_rewrite_queries", fake_rewrite_queries)
    monkeypatch.setattr(engine, "_consolidate_retrieval_entries", lambda entries, **_: entries)

    retrieval, _ = engine._retrieve_memory(
        collection=_RecordingCollection(),
        conversation_id="conv1",
        queries=["q1", "q2"],
        top_k=5,
        reranker_model=_DummyReranker(),  # type: ignore[arg-type]
    )

    contents = {entry.content for entry in retrieval.entries}
    assert "q1 content" in contents
    assert "q2 content" in contents
    assert call_count == 4  # two queries across conversation and global


@pytest.mark.asyncio
async def test_retrieve_memory_dedupes_by_fact_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """If multiple facts share a fact_key, only the newest should be considered."""
    now = datetime.now(UTC)
    older = StoredMemory(
        id="old",
        content="Jane is my wife",
        metadata=MemoryMetadata(
            conversation_id="conv1",
            role="memory",
            created_at=(now - timedelta(minutes=10)).isoformat(),
            salience=0.5,
            fact_key="jane::is my wife",
        ),
        distance=0.1,
    )
    newer = StoredMemory(
        id="new",
        content="Jane Smith is my wife",
        metadata=MemoryMetadata(
            conversation_id="conv1",
            role="memory",
            created_at=now.isoformat(),
            salience=0.9,
            fact_key="jane::is my wife",
        ),
        distance=0.2,
    )

    monkeypatch.setattr(engine, "query_memories", lambda *_args, **_kwargs: [older, newer])
    monkeypatch.setattr(engine, "predict_relevance", lambda _model, pairs: [0.5 for _ in pairs])

    retrieval, _ = engine._retrieve_memory(
        collection=_RecordingCollection(),
        conversation_id="conv1",
        queries=["Who is Jane?"],
        top_k=5,
        reranker_model=_DummyReranker(),  # type: ignore[arg-type]
        include_global=False,
    )

    assert len(retrieval.entries) == 1
    assert retrieval.entries[0].content == "Jane Smith is my wife"


@pytest.mark.asyncio
async def test_process_chat_request_summarizes_and_persists(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _RecordingCollection()
    monkeypatch.setattr(engine, "_consolidate_retrieval_entries", lambda entries, **_: entries)

    async def fake_rewrite_queries(*_args: Any, **_kwargs: Any) -> list[str]:
        return ["Hello rewrite"]

    monkeypatch.setattr(engine, "_rewrite_queries", fake_rewrite_queries)

    async def fake_forward_request(
        _request: Any,
        _base_url: str,
        _api_key: str | None = None,
    ) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "assistant reply"}}]}

    monkeypatch.setattr(engine, "_forward_request", fake_forward_request)

    async def fake_agent_run(self, prompt_text: str, *_args: Any, **_kwargs: Any) -> Any:  # noqa: ANN001, ARG001
        class _Result:
            def __init__(self, output: Any) -> None:
                self.output = output

        if "New facts:" in prompt_text:
            return _Result(engine.SummaryOutput(summary="summary up to 256"))
        return _Result(engine.SummaryOutput(summary=""))

    async def fake_extract_with_pydantic_ai(**_kwargs: Any) -> list[Any]:
        return [
            engine.FactOutput(
                subject="user",
                predicate="likes",
                object="cats",
                fact="User likes cats.",
            ),
            engine.FactOutput(
                subject="user",
                predicate="hobby",
                object="biking",
                fact="User loves biking.",
            ),
        ]

    monkeypatch.setattr(engine, "_extract_with_pydantic_ai", fake_extract_with_pydantic_ai)
    monkeypatch.setattr(engine.Agent, "run", fake_agent_run)
    monkeypatch.setattr(engine, "predict_relevance", lambda _model, pairs: [0.1 for _ in pairs])

    request = ChatRequest(
        model="demo-model",
        messages=[Message(role="user", content="Hello, I enjoy biking in the city.")],
    )

    response = await engine.process_chat_request(
        request,
        collection=collection,
        memory_root=tmp_path,
        openai_base_url="http://mock-llm",
        reranker_model=_DummyReranker(),  # type: ignore[arg-type]
        api_key=None,
        default_top_k=3,
        enable_summarization=True,
        max_entries=10,
    )

    await tasks.wait_for_background_tasks()

    files = list(tmp_path.glob("entries/**/*.md"))
    assert len(files) == 6  # user + assistant + 2 facts + 2 summaries

    # All persisted entries were upserted into the collection as well
    roles = {meta.get("role") for _, meta in collection._store.values()}
    assert {"user", "assistant", "memory", "summary_short", "summary_long"} <= roles

    assert response["choices"][0]["message"]["content"] == "assistant reply"
    assert "memory_hits" in response


def test_evict_if_needed_drops_oldest(monkeypatch: pytest.MonkeyPatch) -> None:
    removed: list[str] = []

    entries = [
        StoredMemory(
            id="old",
            content="old",
            metadata=MemoryMetadata(
                conversation_id="conv",
                role="memory",
                created_at="2023-01-01T00:00:00",
            ),
        ),
        StoredMemory(
            id="new",
            content="new",
            metadata=MemoryMetadata(
                conversation_id="conv",
                role="memory",
                created_at="2024-01-01T00:00:00",
            ),
        ),
    ]

    monkeypatch.setattr(
        engine,
        "list_conversation_entries",
        lambda _collection, _cid, include_summary=False: entries,  # noqa: ARG005
    )
    monkeypatch.setattr(engine, "delete_entries", lambda _collection, ids: removed.extend(ids))

    engine._evict_if_needed(_RecordingCollection(), "conv", max_entries=1)

    assert removed == ["old"]


@pytest.mark.asyncio
async def test_streaming_request_persists_user_and_assistant(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _RecordingCollection()
    request = ChatRequest(
        model="demo-model",
        messages=[Message(role="user", content="Jane is my wife.")],
        stream=True,
    )

    monkeypatch.setattr(engine, "predict_relevance", lambda _model, pairs: [0.0 for _ in pairs])
    monkeypatch.setattr(
        engine.streaming,
        "httpx",
        type("H", (), {"AsyncClient": _DummyAsyncClient}),
    )  # type: ignore[attr-defined]

    async def fake_stream_chat_sse(*_args: Any, **_kwargs: Any) -> Any:
        body = [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            "data: [DONE]",
        ]
        for line in body:
            yield line

    monkeypatch.setattr(engine.streaming, "stream_chat_sse", fake_stream_chat_sse)

    response = await engine.process_chat_request(
        request,
        collection=collection,
        memory_root=tmp_path,
        openai_base_url="http://mock-llm",
        reranker_model=_DummyReranker(),  # type: ignore[arg-type]
        enable_summarization=False,
    )

    chunks = [
        chunk if isinstance(chunk, bytes) else chunk.encode()
        async for chunk in response.body_iterator  # type: ignore[attr-defined]
    ]
    body = b"".join(chunks)
    assert b"Hello" in body

    # Allow background persistence task to run
    await tasks.wait_for_background_tasks()

    files = list(tmp_path.glob("entries/**/*.md"))
    assert len(files) == 2  # user + assistant persisted for streaming, too


@pytest.mark.asyncio
async def test_streaming_with_summarization_persists_facts_and_summaries(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _RecordingCollection()
    request = ChatRequest(
        model="demo-model",
        messages=[Message(role="user", content="My cat is Luna.")],
        stream=True,
    )

    monkeypatch.setattr(engine, "predict_relevance", lambda _model, pairs: [0.0 for _ in pairs])

    async def fake_stream_chat_sse(*_args: Any, **_kwargs: Any) -> Any:
        body = [
            'data: {"choices":[{"delta":{"content":"Sure, noted."}}]}',
            "data: [DONE]",
        ]
        for line in body:
            yield line

    async def fake_extract_with_pydantic_ai(**_kwargs: Any) -> list[Any]:
        return [
            engine.FactOutput(
                subject="user",
                predicate="pet",
                object="Luna",
                fact="User has a cat named Luna.",
            ),
        ]

    async def fake_agent_run(_agent: Any, prompt_text: str, *_args: Any, **_kwargs: Any) -> Any:
        class _Result:
            def __init__(self, output: Any) -> None:
                self.output = output

        if "New facts:" in prompt_text:
            return _Result(engine.SummaryOutput(summary="summary text"))
        return _Result(engine.SummaryOutput(summary=""))

    monkeypatch.setattr(engine.streaming, "stream_chat_sse", fake_stream_chat_sse)
    monkeypatch.setattr(engine.Agent, "run", fake_agent_run)
    monkeypatch.setattr(engine, "_extract_with_pydantic_ai", fake_extract_with_pydantic_ai)

    response = await engine.process_chat_request(
        request,
        collection=collection,
        memory_root=tmp_path,
        openai_base_url="http://mock-llm",
        reranker_model=_DummyReranker(),  # type: ignore[arg-type]
        enable_summarization=True,
    )

    _ = [chunk async for chunk in response.body_iterator]  # type: ignore[attr-defined]
    await tasks.wait_for_background_tasks()

    files = list(tmp_path.glob("entries/**/*.md"))
    assert len(files) == 5  # user + assistant + fact + 2 summaries
    assert any("facts" in str(f) for f in files)
    assert any("summaries/short" in str(f) for f in files)
    assert any("summaries/long" in str(f) for f in files)
