"""Integration-ish test for memory proxy without hitting real LLMs."""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_cli.constants import DEFAULT_OPENAI_EMBEDDING_MODEL
from agent_cli.memory import api as memory_api


class _DummyReranker:
    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [1.0 for _ in pairs]


class _FakeCollection:
    """Minimal Chroma-like collection for testing."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, dict[str, Any]]] = {}

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        for doc_id, doc, meta in zip(ids, documents, metadatas, strict=False):
            self._store[doc_id] = (doc, meta)

    def query(
        self,
        *,
        query_texts: list[str],  # noqa: ARG002
        n_results: int,
        where: dict[str, Any],
        include: list[str] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        # Simple filter by conversation_id
        conv = where.get("conversation_id")
        items = [
            (doc_id, doc, meta)
            for doc_id, (doc, meta) in self._store.items()
            if meta.get("conversation_id") == conv
        ]
        docs = [doc for _, doc, _ in items][:n_results]
        metas = [meta for _, _, meta in items][:n_results]
        ids = [doc_id for doc_id, _, _ in items][:n_results]
        return {
            "documents": [docs],
            "metadatas": [metas],
            "ids": [ids],
            "distances": [[0.0] * len(docs)],
            "embeddings": [[[0.0] for _ in docs]],
        }

    def get(
        self,
        *,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        if where is None:
            return {"documents": [], "metadatas": [], "ids": []}
        results: list[tuple[str, tuple[str, dict[str, Any]]]] = []
        for doc_id, (doc, meta) in self._store.items():
            match = all(
                meta.get(k) == v for clause in where.get("$and", [where]) for k, v in clause.items()
            )
            if match:
                results.append((doc_id, (doc, meta)))
        docs = [doc for _, (doc, _) in results]
        metas = [meta for _, (_, meta) in results]
        ids = [doc_id for doc_id, _ in results]
        return {"documents": [docs], "metadatas": [metas], "ids": ids}

    def delete(self, ids: list[str] | None = None, where: dict[str, Any] | None = None) -> None:
        if ids:
            for doc_id in ids:
                self._store.pop(doc_id, None)
        elif where and "file_path" in where:
            pass  # not needed for memory test


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Create a memory proxy client with all network calls stubbed."""

    async def _noop_watch(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def _fake_forward_request(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "pong"}}]}

    async def _noop_commit(*_args: Any, **_kwargs: Any) -> None:
        return None

    with ExitStack() as stack:
        stack.enter_context(
            patch("agent_cli.memory.client.watch_memory_store", side_effect=_noop_watch),
        )
        stack.enter_context(
            patch("agent_cli.memory.client.get_reranker_model", return_value=_DummyReranker()),
        )
        stack.enter_context(
            patch(
                "agent_cli.memory.engine.forward_chat_request",
                side_effect=_fake_forward_request,
            ),
        )
        stack.enter_context(
            patch("agent_cli.memory.client.init_memory_collection", return_value=_FakeCollection()),
        )
        stack.enter_context(patch("agent_cli.memory.client.init_repo"))
        stack.enter_context(
            patch("agent_cli.memory.engine.commit_changes", side_effect=_noop_commit),
        )
        app = memory_api.create_app(
            memory_path=tmp_path,
            openai_base_url="http://mock-llm",
            embedding_model=DEFAULT_OPENAI_EMBEDDING_MODEL,
            enable_summarization=False,
            default_top_k=2,
        )
        client = TestClient(app)
        yield client


def test_memory_round_trip_creates_files(client: TestClient, tmp_path: Path) -> None:
    """Posting chat completions persists user+assistant turns as MD files."""
    payload = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "Hello there"}],
    }

    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200

    entries_dir = tmp_path / "entries"
    files = list(entries_dir.rglob("*.md"))
    assert len(files) == 2  # user + assistant turns

    content = files[0].read_text(encoding="utf-8")
    assert "---" in content  # YAML front matter present
