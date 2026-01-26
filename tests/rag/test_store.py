"""Tests for RAG store."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_cli.constants import DEFAULT_OPENAI_EMBEDDING_MODEL
from agent_cli.core import chroma
from agent_cli.rag import _store


def test_init_collection(tmp_path: Path) -> None:
    """Test collection initialization."""
    with (
        patch("chromadb.PersistentClient") as mock_client,
        patch("chromadb.utils.embedding_functions.OpenAIEmbeddingFunction") as mock_openai,
    ):
        chroma.init_collection(
            tmp_path,
            name="docs",
            embedding_model=DEFAULT_OPENAI_EMBEDDING_MODEL,
        )

        mock_client.assert_called_once()
        mock_openai.assert_called_once()
        mock_client.return_value.get_or_create_collection.assert_called_once()


def test_delete_by_file_path() -> None:
    """Test deleting by file path."""
    mock_collection = MagicMock()
    _store.delete_by_file_path(mock_collection, "path/to/file")
    mock_collection.delete.assert_called_with(where={"file_path": "path/to/file"})
