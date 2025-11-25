"""Tests for RagClient."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from agent_cli.rag.client import RagClient

if TYPE_CHECKING:
    from pathlib import Path


class _DummyReranker:
    """Dummy reranker for testing."""

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [1.0 for _ in pairs]


class _FakeCollection:
    """Minimal Chroma-like collection for testing."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, dict[str, Any]]] = {}

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        for doc_id, doc, meta in zip(ids, documents, metadatas, strict=False):
            self._store[doc_id] = (doc, meta)

    def query(
        self,
        *,
        query_texts: list[str],  # noqa: ARG002
        n_results: int,
        include: list[str] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        items = list(self._store.items())[:n_results]
        docs = [doc for _, (doc, _) in items]
        metas = [meta for _, (_, meta) in items]
        ids = [doc_id for doc_id, _ in items]
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
        include: list[str] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        docs = [doc for _, (doc, _) in self._store.values()]
        metas = [meta for _, (_, meta) in self._store.values()]
        ids = list(self._store.keys())
        return {"documents": docs, "metadatas": metas, "ids": ids}

    def count(self) -> int:
        return len(self._store)

    def delete(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> None:
        if ids:
            for doc_id in ids:
                self._store.pop(doc_id, None)


@pytest.fixture
def rag_client(tmp_path: Path) -> Any:
    """Create a RagClient for testing with mocked dependencies."""
    with (
        patch(
            "agent_cli.rag.client.init_collection",
            return_value=_FakeCollection(),
        ),
        patch(
            "agent_cli.rag.client.get_reranker_model",
            return_value=_DummyReranker(),
        ),
        patch(
            "agent_cli.rag.client.load_hashes_from_metadata",
            return_value={},
        ),
    ):
        docs_folder = tmp_path / "docs"
        docs_folder.mkdir()
        chroma_path = tmp_path / "chroma"

        client = RagClient(
            docs_folder=docs_folder,
            chroma_path=chroma_path,
            openai_base_url="http://localhost:8080",
            start_watcher=False,
        )
        yield client


def test_list_files_empty(rag_client: Any) -> None:
    """Test listing files when index is empty."""
    files = rag_client.list_files()
    assert files == []


def test_reindex_non_blocking(rag_client: Any) -> None:
    """Test non-blocking reindex."""
    with patch("agent_cli.rag.client.initial_index") as mock_index:
        rag_client.reindex(blocking=False)
        # Give the thread time to start
        time.sleep(0.1)
        mock_index.assert_called_once()


def test_reindex_blocking(rag_client: Any) -> None:
    """Test blocking reindex."""
    with patch("agent_cli.rag.client.initial_index") as mock_index:
        rag_client.reindex(blocking=True)
        mock_index.assert_called_once()


def test_client_initialization(tmp_path: Path) -> None:
    """Test client initialization creates docs folder."""
    docs_folder = tmp_path / "new_docs"
    chroma_path = tmp_path / "chroma"

    assert not docs_folder.exists()

    with (
        patch(
            "agent_cli.rag.client.init_collection",
            return_value=_FakeCollection(),
        ),
        patch(
            "agent_cli.rag.client.get_reranker_model",
            return_value=_DummyReranker(),
        ),
        patch(
            "agent_cli.rag.client.load_hashes_from_metadata",
            return_value={},
        ),
    ):
        RagClient(
            docs_folder=docs_folder,
            chroma_path=chroma_path,
            openai_base_url="http://localhost:8080",
            start_watcher=False,
        )

    assert docs_folder.exists()


def test_client_attributes(rag_client: Any) -> None:
    """Test client has expected attributes."""
    assert rag_client.default_top_k == 3
    assert rag_client.enable_rag_tools is True
    assert rag_client.openai_base_url == "http://localhost:8080"
    assert rag_client.chat_api_key is None
