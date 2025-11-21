"""HTTP-level integration test for the memory API with stubbed LLM calls.

This spins up the FastAPI app created by `create_app` and exercises the
`/v1/chat/completions` endpoint without bypassing the API layer. External LLM
calls are stubbed so the test is deterministic and offline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

import agent_cli.memory.api as memory_api
import agent_cli.rag.retriever as rag_retriever
from agent_cli.memory import engine

if TYPE_CHECKING:
    from agent_cli.memory.models import ChatRequest

if TYPE_CHECKING:
    from pathlib import Path


class _RecordingCollection:
    """Minimal in-memory Chroma-like collection for tests."""

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
        conv = None
        if "$and" in where:
            for clause in where["$and"]:
                if "conversation_id" in clause:
                    conv = clause["conversation_id"]
        else:
            conv = where.get("conversation_id")
        items = [
            (doc_id, doc, meta)
            for doc_id, (doc, meta) in self._store.items()
            if meta.get("conversation_id") == conv and meta.get("role") == "memory"
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
        _include: list[str] | None = None,
    ) -> dict[str, Any]:
        if where is None:
            return {"documents": [], "metadatas": [], "ids": []}
        clauses = where.get("$and", [where])  # type: ignore[arg-type]

        def _matches(meta: dict[str, Any], clause: dict[str, Any]) -> bool:
            for key, value in clause.items():
                if isinstance(value, dict) and "$ne" in value and meta.get(key) == value["$ne"]:
                    return False
                if meta.get(key) != value:
                    return False
            return True

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


class _DummyReranker:
    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [1.0 for _ in pairs]


def _make_request_json(text: str) -> dict[str, Any]:
    return {
        "model": "demo-model",
        "messages": [
            {"role": "user", "content": text},
        ],
    }


@pytest.mark.asyncio
async def test_memory_api_updates_latest_fact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end through the HTTP API with stubbed LLMs; latest fact should replace previous."""
    collection = _RecordingCollection()

    # Patch out external dependencies and watchers.
    monkeypatch.setattr(memory_api, "init_memory_collection", lambda *_args, **_kwargs: collection)
    monkeypatch.setattr(rag_retriever, "get_reranker_model", lambda: _DummyReranker())

    async def _noop_watch(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(memory_api, "watch_memory_store", _noop_watch)

    async def fake_forward_request(_request: ChatRequest, *_args: Any, **_kwargs: Any) -> Any:
        return {"choices": [{"message": {"content": "ok"}}]}

    async def fake_extract_with_pydantic_ai(**kwargs: Any) -> list[str]:
        transcript = kwargs.get("transcript") or ""
        return [transcript] if transcript else []

    async def fake_rewrite_queries(user_message: str, **_kwargs: Any) -> list[str]:
        return [user_message]

    async def fake_reconcile(
        _collection: Any,
        _conversation_id: str,
        new_facts: list[str],
        **_kwargs: Any,
    ) -> tuple[list[str], list[str]]:
        """Latest wins: delete all existing, add new facts."""
        existing_ids = list(getattr(_collection, "_store", {}).keys())
        return new_facts, existing_ids

    def fake_delete_entries(coll: Any, ids: list[str]) -> None:
        coll.delete(ids=ids)

    def fake_upsert_memories(
        coll: Any,
        ids: list[str],
        contents: list[str],
        metadatas: list[Any],
    ) -> None:
        coll.upsert(ids, contents, [dict(m) for m in metadatas])

    async def fake_update_summaries(**_kwargs: Any) -> tuple[str | None, str | None]:
        return "short", "long"

    monkeypatch.setattr(engine, "_forward_request", fake_forward_request)
    monkeypatch.setattr(engine, "_extract_with_pydantic_ai", fake_extract_with_pydantic_ai)
    monkeypatch.setattr(engine, "_rewrite_queries", fake_rewrite_queries)
    monkeypatch.setattr(engine, "_reconcile_facts", fake_reconcile)
    monkeypatch.setattr(engine, "delete_entries", fake_delete_entries)
    monkeypatch.setattr(engine, "upsert_memories", fake_upsert_memories)
    monkeypatch.setattr(engine, "_update_summaries", fake_update_summaries)

    app = memory_api.create_app(
        memory_path=tmp_path / "memory_db",
        openai_base_url="http://llm",
        embedding_model="text-embedding-3-small",
        embedding_api_key=None,
        chat_api_key=None,
        enable_summarization=True,
    )

    with TestClient(app) as client:
        resp1 = client.post("/v1/chat/completions", json=_make_request_json("my wife is Jane"))
        assert resp1.status_code == 200

        resp2 = client.post("/v1/chat/completions", json=_make_request_json("my wife is Anne"))
        assert resp2.status_code == 200

    mems = [
        (doc_id, doc, meta)
        for doc_id, (doc, meta) in collection._store.items()
        if meta.get("role") == "memory"
    ]
    # Only the latest (Anne) should remain.
    assert len(mems) == 1
    _doc_id, doc, meta = mems[0]
    assert "Anne" in doc
    assert meta.get("conversation_id") == "default"
