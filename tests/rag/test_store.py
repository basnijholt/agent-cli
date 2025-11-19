"""Tests for RAG store."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_cli.rag import store


def test_init_collection(tmp_path: Path) -> None:
    """Test collection initialization."""
    with (
        patch("chromadb.PersistentClient") as mock_client,
        patch("agent_cli.rag.store.embedding_functions.OpenAIEmbeddingFunction") as mock_openai,
    ):
        store.init_collection(tmp_path, embedding_model="text-embedding-3-small")

        mock_client.assert_called_once()
        mock_openai.assert_called_once()
        mock_client.return_value.get_or_create_collection.assert_called_once()


def test_upsert_docs() -> None:
    """Test upserting documents."""
    mock_collection = MagicMock()
    store.upsert_docs(
        mock_collection,
        ids=["1"],
        documents=["text"],
        metadatas=[{"source": "s"}],
    )
    mock_collection.upsert.assert_called_once()

    # Test empty
    mock_collection.reset_mock()
    store.upsert_docs(mock_collection, [], [], [])
    mock_collection.upsert.assert_not_called()


def test_delete_by_file_path() -> None:
    """Test deleting by file path."""
    mock_collection = MagicMock()
    store.delete_by_file_path(mock_collection, "path/to/file")
    mock_collection.delete.assert_called_with(where={"file_path": "path/to/file"})
