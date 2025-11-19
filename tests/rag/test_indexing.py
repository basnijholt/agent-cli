"""Tests for RAG indexing logic."""

import shutil
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.rag import indexing
from agent_cli.rag.utils import get_file_hash


@pytest.fixture
def mock_collection() -> MagicMock:
    """Mock Chroma collection."""
    return MagicMock()


@pytest.fixture
def temp_docs_folder(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temp docs folder."""
    folder = tmp_path / "docs"
    folder.mkdir()
    yield folder
    if folder.exists():
        shutil.rmtree(folder)


def test_index_file(mock_collection: MagicMock, temp_docs_folder: Path) -> None:
    """Test indexing a file."""
    file_path = temp_docs_folder / "test.txt"
    file_path.write_text("Hello world.", encoding="utf-8")

    file_hashes: dict[str, str] = {}

    # Patch utils to ensure we don't rely on real chunking logic complexity
    # We patch where it is IMPORTED in indexing.py
    with patch("agent_cli.rag.indexing.chunk_text", return_value=["Hello world."]):
        indexing.index_file(mock_collection, temp_docs_folder, file_path, file_hashes)

    # Should have upserted
    mock_collection.upsert.assert_called_once()
    # Should have updated hashes
    assert "test.txt" in file_hashes


def test_index_file_no_change(mock_collection: MagicMock, temp_docs_folder: Path) -> None:
    """Test indexing unchanged file."""
    file_path = temp_docs_folder / "test.txt"
    file_path.write_text("Hello world.", encoding="utf-8")

    # Pre-fill hash
    current_hash = get_file_hash(file_path)
    file_hashes = {"test.txt": current_hash}

    indexing.index_file(mock_collection, temp_docs_folder, file_path, file_hashes)

    # Should NOT upsert
    mock_collection.upsert.assert_not_called()
