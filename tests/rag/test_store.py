"""Tests for RAG store (ChromaDB wrapper)."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.rag import store

# Check if chromadb is installed
try:
    import chromadb
except ImportError:
    chromadb = None


@pytest.fixture
def mock_chroma_client() -> Generator[MagicMock, None, None]:
    """Mock ChromaDB client."""
    with patch("agent_cli.rag.store.chromadb") as mock_chromadb:
        mock_client = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client
        yield mock_client


@pytest.mark.skipif(chromadb is None, reason="chromadb not installed")
def test_init_collection(mock_chroma_client: MagicMock, tmp_path: Path) -> None:
    """Test initializing collection."""
    mock_collection = MagicMock()
    mock_chroma_client.get_or_create_collection.return_value = mock_collection

    # Mock embedding function to prevent download
    with patch("agent_cli.rag.store.embedding_functions.SentenceTransformerEmbeddingFunction"):
        coll = store.init_collection(tmp_path)

        assert coll == mock_collection
        mock_chroma_client.get_or_create_collection.assert_called_once()


@pytest.mark.skipif(chromadb is None, reason="chromadb not installed")
def test_upsert_docs() -> None:
    """Test upserting docs."""
    mock_collection = MagicMock()

    store.upsert_docs(
        mock_collection,
        ids=["1"],
        documents=["doc"],
        metadatas=[{"key": "val"}],
    )

    mock_collection.upsert.assert_called_once_with(
        ids=["1"],
        documents=["doc"],
        metadatas=[{"key": "val"}],
    )


@pytest.mark.skipif(chromadb is None, reason="chromadb not installed")
def test_delete_by_file_path() -> None:
    """Test deleting by file path."""
    mock_collection = MagicMock()

    store.delete_by_file_path(mock_collection, "folder/file.txt")

    mock_collection.delete.assert_called_once_with(where={"file_path": "folder/file.txt"})
