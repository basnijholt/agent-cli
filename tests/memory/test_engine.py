"""Unit/integration coverage for the memory engine."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from typing import Any, Self
from uuid import uuid4

import pytest

from agent_cli.memory import _ingest, _persistence, _retrieval, _tasks, engine
from agent_cli.memory._files import (
    ensure_store_dirs,
    load_snapshot,
    write_memory_file,
    write_snapshot,
)
from agent_cli.memory.entities import Fact
from agent_cli.memory.models import (
    ChatRequest,
    MemoryMetadata,
    Message,
    StoredMemory,
    SummaryOutput,
)


class _DummyReranker:
    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Return uniform relevance for all pairs."""
        return [1.0 for _ in pairs]


class _RecordingCollection:
    """Minimal Chroma-like collection that keeps everything in memory."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, dict[str, Any], list[float]]] = {}

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        for doc_id, doc, meta in zip(ids, documents, metadatas, strict=False):
            self._store[doc_id] = (doc, dict(meta), [0.0])

    def query(
        self,
        *,
        query_texts: list[str],  # noqa: ARG002
        n_results: int,
        where: dict[str, Any],
        include: list[str] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        conv = where.get("conversation_id")
        items = [
            (doc_id, doc, meta, emb)
            for doc_id, (doc, meta, emb) in self._store.items()
            if meta.get("conversation_id") == conv
        ]
        ids = [doc_id for doc_id, _, _, _ in items][:n_results]
        docs = [doc for _, doc, _, _ in items][:n_results]
        metas = [meta for _, _, meta, _ in items][:n_results]
        embeddings = [emb for _, _, _, emb in items][:n_results]
        return {
            "documents": [docs],
            "metadatas": [metas],
            "ids": [ids],
            "distances": [[0.0 for _ in ids]],
            "embeddings": [embeddings],
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
            for doc_id, (doc, meta, _emb) in self._store.items()
            if all(_matches(meta, clause) for clause in clauses)
        ]
        docs = [doc for _, (doc, _) in results]
        metas = [meta for _, (_, meta) in results]
        ids = [doc_id for doc_id, _ in results]
        return {"documents": [docs], "metadatas": [metas], "ids": ids}


@pytest.fixture
def stub_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shim out OpenAI provider/model classes for agent construction."""
    import pydantic_ai.models.openai  # noqa: PLC0415
    import pydantic_ai.providers.openai  # noqa: PLC0415
    import pydantic_ai.settings  # noqa: PLC0415

    class _DummyProvider:
        pass

    class _DummyModel:
        pass

    class _DummySettings:
        def __init__(self, **_kwargs: Any) -> None:
            return

    monkeypatch.setattr(
        pydantic_ai.providers.openai,
        "OpenAIProvider",
        lambda *_args, **_kwargs: _DummyProvider(),
    )
    monkeypatch.setattr(
        pydantic_ai.models.openai,
        "OpenAIChatModel",
        lambda *_args, **_kwargs: _DummyModel(),
    )
    monkeypatch.setattr(pydantic_ai.settings, "ModelSettings", lambda **_kwargs: _DummySettings())


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
    is_closed = False

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
async def test_augment_chat_request_disables_with_zero_top_k() -> None:
    """Explicit memory_top_k=0 should skip retrieval and leave request untouched."""
    request = ChatRequest(
        model="x",
        messages=[Message(role="user", content="hello")],
        memory_top_k=0,
    )

    aug_request, retrieval_res, conversation_id, summaries = await _retrieval.augment_chat_request(
        request,
        collection=_RecordingCollection(),
        reranker_model=_DummyReranker(),  # type: ignore[arg-type]
    )

    assert retrieval_res is None
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
        filters: dict[str, Any] | None = None,  # noqa: ARG001
    ) -> list[StoredMemory]:
        nonlocal call_count
        call_count += 1
        return [mem_primary, mem_similar] if conversation_id == "conv1" else [mem_diverse]

    monkeypatch.setattr(_retrieval, "query_memories", fake_query_memories)
    monkeypatch.setattr(
        _retrieval,
        "predict_relevance",
        lambda _model, pairs: [0.9, 0.1, 0.8][: len(pairs)],
    )
    monkeypatch.setattr(
        _retrieval,
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

    retrieval_res, summaries = _retrieval.retrieve_memory(
        collection=_RecordingCollection(),
        conversation_id="conv1",
        query="I enjoy biking and also travel planning",
        top_k=2,
        reranker_model=_DummyReranker(),  # type: ignore[arg-type]
        # Use defaults for recency/threshold to ensure they don't filter out our test data
    )

    contents = [entry.content for entry in retrieval_res.entries]
    assert len(contents) == 2
    assert mem_primary.content in contents
    assert mem_diverse.content in contents  # diverse item beats near-duplicate
    assert any("Conversation summary" in text for text in summaries)
    assert call_count == 2  # conversation + global


@pytest.mark.asyncio
async def test_retrieve_memory_returns_all_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    """All facts are returned (no dedupe)."""
    now = datetime.now(UTC)
    older = StoredMemory(
        id="old",
        content="Jane is my wife",
        metadata=MemoryMetadata(
            conversation_id="conv1",
            role="memory",
            created_at=(now - timedelta(minutes=10)).isoformat(),
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
            fact_key="jane::is my wife",
        ),
        distance=0.2,
    )

    monkeypatch.setattr(_retrieval, "query_memories", lambda *_args, **_kwargs: [older, newer])
    # Relevance > 0.35 default
    monkeypatch.setattr(_retrieval, "predict_relevance", lambda _model, pairs: [2.0 for _ in pairs])

    retrieval_res, _ = _retrieval.retrieve_memory(
        collection=_RecordingCollection(),
        conversation_id="conv1",
        query="Who is Jane?",
        top_k=5,
        reranker_model=_DummyReranker(),  # type: ignore[arg-type]
        include_global=False,
    )

    assert len(retrieval_res.entries) == 2


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Flaky on Windows due to SSL cert loading timeouts",
)
async def test_process_chat_request_summarizes_and_persists(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _RecordingCollection()

    async def fake_forward_request(
        _request: Any,
        _base_url: str,
        _api_key: str | None = None,
        exclude_fields: set[str] | None = None,  # noqa: ARG001
    ) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "assistant reply"}}]}

    monkeypatch.setattr(engine, "forward_chat_request", fake_forward_request)

    async def fake_agent_run(self, prompt_text: str, *_args: Any, **_kwargs: Any) -> Any:  # noqa: ANN001, ARG001
        class _Result:
            def __init__(self, output: Any) -> None:
                self.output = output

        prompt_str = str(prompt_text)
        if "New facts:" in prompt_str:
            return _Result(SummaryOutput(summary="summary up to 256"))
        if "Hello, I enjoy biking" in prompt_str:
            return _Result(["User likes cats.", "User loves biking."])
        return _Result(SummaryOutput(summary="noop"))

    async def fake_reconcile(
        _collection: Any,
        _conversation_id: str,
        new_facts: list[str],
        **_kwargs: Any,
    ) -> tuple[list[Fact], list[str], dict[str, str]]:
        entries = [
            Fact(
                id=str(uuid4()),
                conversation_id=_conversation_id,
                content=f,
                source_id="source-id",
                created_at=datetime.now(UTC),
            )
            for f in new_facts
        ]
        return entries, [], {}

    monkeypatch.setattr(_ingest, "reconcile_facts", fake_reconcile)
    import pydantic_ai  # noqa: PLC0415

    monkeypatch.setattr(pydantic_ai.Agent, "run", fake_agent_run)
    # High relevance so they aren't filtered
    monkeypatch.setattr(_retrieval, "predict_relevance", lambda _model, pairs: [5.0 for _ in pairs])

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

    await _tasks.wait_for_background_tasks()

    files = list(tmp_path.glob("entries/**/*.md"))
    assert len(files) == 5  # user + assistant + 2 facts + 1 summary (single)

    # All persisted entries were upserted into the collection as well
    roles = {meta.get("role") for _, meta, _ in collection._store.values()}
    assert {"user", "assistant", "memory", "summary"} <= roles

    assert response["choices"][0]["message"]["content"] == "assistant reply"
    assert "memory_hits" in response


def test_evict_if_needed_drops_oldest_and_cleans_disk(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    old_record = write_memory_file(
        tmp_path,
        conversation_id="conv",
        role="memory",
        created_at="2023-01-01T00:00:00",
        content="old",
        doc_id="old",
    )
    new_record = write_memory_file(
        tmp_path,
        conversation_id="conv",
        role="memory",
        created_at="2024-01-01T00:00:00",
        content="new",
        doc_id="new",
    )
    _, snapshot_path = ensure_store_dirs(tmp_path)
    write_snapshot(snapshot_path, [old_record, new_record])

    removed: list[str] = []
    monkeypatch.setattr(
        _persistence,
        "list_conversation_entries",
        lambda _collection, _cid, include_summary=False: entries,  # noqa: ARG005
    )
    monkeypatch.setattr(
        _persistence,
        "delete_entries",
        lambda _collection, ids: removed.extend(ids),
    )

    _persistence.evict_if_needed(_RecordingCollection(), tmp_path, "conv", 1)

    snapshot = load_snapshot(snapshot_path)

    assert removed == ["old"]
    assert not old_record.path.exists()
    assert new_record.path.exists()
    assert "old" not in snapshot
    assert "new" in snapshot


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="SSL context creation times out on Windows CI",
)
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

    # High score
    monkeypatch.setattr(_retrieval, "predict_relevance", lambda _model, pairs: [5.0 for _ in pairs])

    async def fake_stream_chat_sse(*_args: Any, **_kwargs: Any) -> Any:
        body = [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            "data: [DONE]",
        ]
        for line in body:
            yield line

    async def fake_agent_run(*_args: Any, **_kwargs: Any) -> Any:
        class _Result:
            def __init__(self, output: Any) -> None:
                self.output = output

        # Return empty facts
        return _Result([])

    monkeypatch.setattr(engine._streaming, "stream_chat_sse", fake_stream_chat_sse)
    import pydantic_ai  # noqa: PLC0415

    monkeypatch.setattr(pydantic_ai.Agent, "run", fake_agent_run)

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
    await _tasks.wait_for_background_tasks()

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

    monkeypatch.setattr(_retrieval, "predict_relevance", lambda _model, pairs: [5.0 for _ in pairs])

    async def fake_stream_chat_sse(*_args: Any, **_kwargs: Any) -> Any:
        body = [
            'data: {"choices":[{"delta":{"content":"Sure, noted."}}]}',
            "data: [DONE]",
        ]
        for line in body:
            yield line

    async def fake_agent_run(_agent: Any, prompt_text: str, *_args: Any, **_kwargs: Any) -> Any:
        class _Result:
            def __init__(self, output: Any) -> None:
                self.output = output

        prompt_str = str(prompt_text)
        if "New facts:" in prompt_str:
            return _Result(SummaryOutput(summary="summary text"))
        if "My cat is Luna" in prompt_str:
            return _Result(["User has a cat named Luna."])
        return _Result(SummaryOutput(summary="noop"))

    monkeypatch.setattr(engine._streaming, "stream_chat_sse", fake_stream_chat_sse)

    async def fake_reconcile(
        _collection: Any,
        _conversation_id: str,
        new_facts: list[str],
        **_kwargs: Any,
    ) -> tuple[list[Fact], list[str], dict[str, str]]:
        entries = [
            Fact(
                id=str(uuid4()),
                conversation_id=_conversation_id,
                content=f,
                source_id="source-id",
                created_at=datetime.now(UTC),
            )
            for f in new_facts
        ]
        return entries, [], {}

    monkeypatch.setattr(_ingest, "reconcile_facts", fake_reconcile)
    import pydantic_ai  # noqa: PLC0415

    monkeypatch.setattr(pydantic_ai.Agent, "run", fake_agent_run)

    response = await engine.process_chat_request(
        request,
        collection=collection,
        memory_root=tmp_path,
        openai_base_url="http://mock-llm",
        reranker_model=_DummyReranker(),  # type: ignore[arg-type]
        enable_summarization=True,
    )

    _ = [chunk async for chunk in response.body_iterator]  # type: ignore[attr-defined]
    await _tasks.wait_for_background_tasks()

    files = list(tmp_path.glob("entries/**/*.md"))
    assert len(files) == 4  # user + assistant + fact + 1 summary
    assert any("facts" in f.parts for f in files)
    assert any(f.parent.name == "summaries" and f.name == "summary.md" for f in files)
