"""Tests for RAG indexing logic."""

import shutil
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.rag import _indexing
from agent_cli.rag._utils import get_file_hash


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
    file_mtimes: dict[str, float] = {}

    # Patch utils to ensure we don't rely on real chunking logic complexity
    with patch("agent_cli.rag._indexing.chunk_text", return_value=["Hello world."]):
        _indexing.index_file(mock_collection, temp_docs_folder, file_path, file_hashes, file_mtimes)

    # Should have upserted
    mock_collection.upsert.assert_called_once()
    # Should have updated hashes and mtimes
    assert "test.txt" in file_hashes
    assert "test.txt" in file_mtimes


def test_index_file_no_change(mock_collection: MagicMock, temp_docs_folder: Path) -> None:
    """Test indexing unchanged file."""
    file_path = temp_docs_folder / "test.txt"
    file_path.write_text("Hello world.", encoding="utf-8")

    # Pre-fill hash and mtime
    current_hash = get_file_hash(file_path)
    current_mtime = file_path.stat().st_mtime
    file_hashes = {"test.txt": current_hash}
    file_mtimes = {"test.txt": current_mtime}

    _indexing.index_file(mock_collection, temp_docs_folder, file_path, file_hashes, file_mtimes)

    # Should NOT upsert (mtime unchanged = fast path skip)
    mock_collection.upsert.assert_not_called()


def test_initial_index_removes_stale(mock_collection: MagicMock, temp_docs_folder: Path) -> None:
    """Test that initial_index removes files present in DB but missing from disk."""
    # Setup: DB thinks "deleted.txt" exists
    file_hashes = {"deleted.txt": "oldhash"}
    file_mtimes: dict[str, float] = {"deleted.txt": 12345.0}

    # Setup: Disk only has "existing.txt"
    (temp_docs_folder / "existing.txt").write_text("I am here.")

    with patch("agent_cli.rag._indexing.chunk_text", return_value=["content"]):
        _indexing.initial_index(mock_collection, temp_docs_folder, file_hashes, file_mtimes)

    # Verify delete called for "deleted.txt"
    mock_collection.delete.assert_called_with(where={"file_path": "deleted.txt"})

    # Verify file_hashes updated
    assert "deleted.txt" not in file_hashes
    assert "existing.txt" in file_hashes


def test_initial_index_ignores_hidden_directories(
    mock_collection: MagicMock,
    temp_docs_folder: Path,
) -> None:
    """Test that initial_index ignores files in hidden directories like .git."""
    # Setup: Create files in hidden directories that should be ignored
    git_dir = temp_docs_folder / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("git config")
    (git_dir / "HEAD").write_text("ref: refs/heads/main")

    venv_dir = temp_docs_folder / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    (venv_dir / "site.py").write_text("# site packages")

    # Setup: Create a valid file that should be indexed
    (temp_docs_folder / "readme.md").write_text("# Readme")

    file_hashes: dict[str, str] = {}
    file_mtimes: dict[str, float] = {}

    with patch("agent_cli.rag._indexing.chunk_text", return_value=["content"]):
        _indexing.initial_index(mock_collection, temp_docs_folder, file_hashes, file_mtimes)

    # Only readme.md should be indexed
    assert "readme.md" in file_hashes
    assert ".git/config" not in file_hashes
    assert ".git/HEAD" not in file_hashes
    assert ".venv/lib/site.py" not in file_hashes


def test_initial_index_ignores_common_dev_directories(
    mock_collection: MagicMock,
    temp_docs_folder: Path,
) -> None:
    """Test that initial_index ignores common development directories."""
    # Setup: Create files in directories that should be ignored
    pycache = temp_docs_folder / "__pycache__"
    pycache.mkdir()
    (pycache / "module.cpython-313.pyc").write_text("bytecode")

    node_modules = temp_docs_folder / "node_modules" / "lodash"
    node_modules.mkdir(parents=True)
    (node_modules / "index.js").write_text("module.exports = {}")

    venv = temp_docs_folder / "venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "activate").write_text("# activate script")

    # Setup: Create a valid file that should be indexed
    (temp_docs_folder / "app.py").write_text("# Application code")

    file_hashes: dict[str, str] = {}
    file_mtimes: dict[str, float] = {}

    with patch("agent_cli.rag._indexing.chunk_text", return_value=["content"]):
        _indexing.initial_index(mock_collection, temp_docs_folder, file_hashes, file_mtimes)

    # Only app.py should be indexed
    assert "app.py" in file_hashes
    assert "__pycache__/module.cpython-313.pyc" not in file_hashes
    assert "node_modules/lodash/index.js" not in file_hashes
    assert "venv/bin/activate" not in file_hashes
