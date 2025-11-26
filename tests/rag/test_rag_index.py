"""Tests for RagIndex."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from agent_cli.rag.index import RagIndex

if TYPE_CHECKING:
    from pathlib import Path


class _DummyReranker:
    """Dummy reranker for testing."""

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        # Return decreasing scores so first doc ranks highest
        return [1.0 - i * 0.1 for i in range(len(pairs))]


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
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        # Filter by where clause
        items = []
        for doc_id, (doc, meta) in self._store.items():
            if where:
                # Simple equality filter
                match = all(meta.get(k) == v for k, v in where.items())
                if not match:
                    continue
            items.append((doc_id, doc, meta))

        items = items[:n_results]
        docs = [doc for _, doc, _ in items]
        metas = [meta for _, _, meta in items]
        ids = [doc_id for doc_id, _, _ in items]
        return {
            "documents": [docs],
            "metadatas": [metas],
            "ids": [ids],
            "distances": [[0.0] * len(docs)],
        }

    def get(
        self,
        *,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        items = []
        for doc_id, (doc, meta) in self._store.items():
            if where:
                match = all(meta.get(k) == v for k, v in where.items())
                if not match:
                    continue
            items.append((doc_id, doc, meta))

        docs = [doc for _, doc, _ in items]
        metas = [meta for _, _, meta in items]
        ids = [doc_id for doc_id, _, _ in items]
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
def rag_index(tmp_path: Path) -> RagIndex:
    """Create a RagIndex for testing with mocked dependencies."""
    with (
        patch(
            "agent_cli.rag.index.init_collection",
            return_value=_FakeCollection(),
        ),
        patch(
            "agent_cli.rag.index.get_reranker_model",
            return_value=_DummyReranker(),
        ),
    ):
        return RagIndex(chroma_path=tmp_path / "chroma")


def test_add_text(rag_index: RagIndex) -> None:
    """Test adding raw text."""
    doc_id = rag_index.add("Hello world, this is a test.")
    assert doc_id is not None
    assert rag_index.count() == 1


def test_add_text_with_metadata(rag_index: RagIndex) -> None:
    """Test adding text with custom metadata."""
    doc_id = rag_index.add(
        "Python is a great language",
        metadata={"source": "chatgpt", "topic": "programming"},
    )
    assert doc_id is not None

    # Verify metadata is stored
    results = rag_index.collection.get(where={"source": "chatgpt"})
    assert len(results["ids"]) == 1
    assert results["metadatas"][0]["topic"] == "programming"


def test_add_text_with_custom_id(rag_index: RagIndex) -> None:
    """Test adding text with a custom document ID."""
    doc_id = rag_index.add("Test content", doc_id="my-custom-id")
    assert doc_id == "my-custom-id"


def test_add_file(rag_index: RagIndex, tmp_path: Path) -> None:
    """Test adding a file."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("This is file content for testing.")

    doc_id = rag_index.add_file(test_file)
    assert doc_id is not None
    assert rag_index.count() == 1

    # Check file metadata
    results = rag_index.collection.get(include=["metadatas"])
    meta = results["metadatas"][0]
    assert meta["source"] == "test.txt"
    assert meta["file_type"] == "txt"


def test_add_file_not_found(rag_index: RagIndex, tmp_path: Path) -> None:
    """Test adding a non-existent file raises error."""
    with pytest.raises(ValueError, match="Could not read file"):
        rag_index.add_file(tmp_path / "nonexistent.txt")


def test_search_basic(rag_index: RagIndex) -> None:
    """Test basic search without filters."""
    rag_index.add("Python is great for data science", metadata={"source": "doc1"})
    rag_index.add("JavaScript is used for web development", metadata={"source": "doc2"})

    results = rag_index.search("Python programming")
    assert results.context != ""
    assert len(results.sources) > 0


def test_search_empty(rag_index: RagIndex) -> None:
    """Test search on empty index."""
    results = rag_index.search("anything")
    assert results.context == ""
    assert results.sources == []


def test_search_with_filters(rag_index: RagIndex) -> None:
    """Test search with metadata filtering."""
    rag_index.add("Python tip from ChatGPT", metadata={"source": "chatgpt"})
    rag_index.add("Python tip from Claude", metadata={"source": "claude"})

    # Search only chatgpt
    results = rag_index.search("Python", filters={"source": "chatgpt"})
    assert len(results.sources) == 1
    assert results.sources[0].source == "chatgpt"


def test_delete_by_id(rag_index: RagIndex) -> None:
    """Test deleting by document ID."""
    doc_id = rag_index.add("Content to delete")
    assert rag_index.count() == 1

    deleted = rag_index.delete(doc_id)
    assert deleted == 1
    assert rag_index.count() == 0


def test_delete_by_metadata(rag_index: RagIndex) -> None:
    """Test deleting by metadata filter."""
    rag_index.add("Old content", metadata={"source": "old"})
    rag_index.add("New content", metadata={"source": "new"})
    assert rag_index.count() == 2

    deleted = rag_index.delete_by_metadata({"source": "old"})
    assert deleted == 1
    assert rag_index.count() == 1


def test_count_no_filter(rag_index: RagIndex) -> None:
    """Test count without filter."""
    assert rag_index.count() == 0

    rag_index.add("Doc 1")
    rag_index.add("Doc 2")
    assert rag_index.count() == 2


def test_count_with_filter(rag_index: RagIndex) -> None:
    """Test count with filter."""
    rag_index.add("ChatGPT doc", metadata={"source": "chatgpt"})
    rag_index.add("Claude doc", metadata={"source": "claude"})

    assert rag_index.count(filters={"source": "chatgpt"}) == 1
    assert rag_index.count(filters={"source": "claude"}) == 1
    assert rag_index.count() == 2


def test_list_sources(rag_index: RagIndex) -> None:
    """Test listing unique sources."""
    rag_index.add("Doc 1", metadata={"source": "chatgpt"})
    rag_index.add("Doc 2", metadata={"source": "claude"})
    rag_index.add("Doc 3", metadata={"source": "chatgpt"})  # duplicate

    sources = rag_index.list_sources()
    assert sources == ["chatgpt", "claude"]  # sorted, deduplicated


def test_list_sources_empty(rag_index: RagIndex) -> None:
    """Test listing sources on empty index."""
    sources = rag_index.list_sources()
    assert sources == []


def test_chunking_long_text(rag_index: RagIndex) -> None:
    """Test that long text is chunked."""
    # Create text longer than default chunk size
    long_text = "This is a sentence. " * 100  # ~2000 chars

    doc_id = rag_index.add(long_text)
    assert doc_id is not None

    # Should have multiple chunks
    assert rag_index.count() > 1

    # All chunks should have same doc_id in metadata
    results = rag_index.collection.get(include=["metadatas"])
    doc_ids = {meta["doc_id"] for meta in results["metadatas"]}
    assert doc_ids == {doc_id}
