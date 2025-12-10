"""Tests for RAG indexer."""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from watchfiles import Change

from agent_cli.rag import _indexer
from agent_cli.rag._utils import should_ignore_path


@pytest.mark.asyncio
async def test_watch_docs(tmp_path: Path) -> None:
    """Test watching docs folder."""
    mock_collection = MagicMock()
    docs_folder = tmp_path / "docs"
    docs_folder.mkdir()
    file_hashes: dict[str, str] = {}
    file_mtimes: dict[str, float] = {}

    # Create dummy files so is_file() returns True
    (docs_folder / "new.txt").touch()
    (docs_folder / "mod.txt").touch()
    # del.txt doesn't need to exist

    # Mock awatch to yield changes
    changes = {
        (Change.added, str(docs_folder / "new.txt")),
        (Change.modified, str(docs_folder / "mod.txt")),
        (Change.deleted, str(docs_folder / "del.txt")),
    }

    async def mock_awatch_gen(
        *_args: Any,
        **_kwargs: Any,
    ) -> AsyncGenerator[set[tuple[Change, str]], None]:
        yield changes

    async def fake_watch_directory(_root: Path, handler: Any, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        for change, path in changes:
            handler(change, Path(path))

    with (
        patch("agent_cli.rag._indexer.watch_directory", side_effect=fake_watch_directory),
        patch("agent_cli.rag._indexer.index_file") as mock_index,
        patch("agent_cli.rag._indexer.remove_file") as mock_remove,
    ):
        await _indexer.watch_docs(mock_collection, docs_folder, file_hashes, file_mtimes)

        # Check calls
        assert mock_index.call_count == 2  # added and modified
        assert mock_remove.call_count == 1  # deleted


@pytest.mark.asyncio
async def test_watch_docs_passes_ignore_filter(tmp_path: Path) -> None:
    """Test that watch_docs passes the should_ignore_path filter to watch_directory."""
    mock_collection = MagicMock()
    docs_folder = tmp_path / "docs"
    docs_folder.mkdir()
    file_hashes: dict[str, str] = {}
    file_mtimes: dict[str, float] = {}

    async def fake_watch_directory(
        _root: Path,
        _handler: Any,
        *,
        ignore_filter: Any = None,
        **_kwargs: Any,
    ) -> None:
        # Verify ignore_filter is provided and is the should_ignore_path function
        assert ignore_filter is not None
        assert ignore_filter.__name__ == "should_ignore_path"

    with patch(
        "agent_cli.rag._indexer.watch_directory",
        side_effect=fake_watch_directory,
    ):
        await _indexer.watch_docs(mock_collection, docs_folder, file_hashes, file_mtimes)


@pytest.mark.asyncio
async def test_watch_docs_ignore_filter_works(tmp_path: Path) -> None:
    """Test that the ignore filter correctly filters out ignored paths."""
    docs_folder = tmp_path / "docs"
    docs_folder.mkdir()

    # Test that the filter correctly identifies paths to ignore
    git_file = docs_folder / ".git" / "config"
    venv_file = docs_folder / "venv" / "bin" / "python"
    pycache_file = docs_folder / "__pycache__" / "module.pyc"
    normal_file = docs_folder / "readme.md"

    assert should_ignore_path(git_file, docs_folder)
    assert should_ignore_path(venv_file, docs_folder)
    assert should_ignore_path(pycache_file, docs_folder)
    assert not should_ignore_path(normal_file, docs_folder)
