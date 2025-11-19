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


def test_initial_index_removes_stale(mock_collection: MagicMock, temp_docs_folder: Path) -> None:
    """Test that initial_index removes files present in DB but missing from disk."""
    # Setup: DB thinks "deleted.txt" exists
    file_hashes = {"deleted.txt": "oldhash"}

    # Setup: Disk only has "existing.txt"
    (temp_docs_folder / "existing.txt").write_text("I am here.")

    with patch("agent_cli.rag.indexing.chunk_text", return_value=["content"]):
        indexing.initial_index(mock_collection, temp_docs_folder, file_hashes)

    # Verify delete called for "deleted.txt"
    mock_collection.delete.assert_called_with(where={"file_path": "deleted.txt"})

    # Verify file_hashes updated
    assert "deleted.txt" not in file_hashes
    assert "existing.txt" in file_hashes
