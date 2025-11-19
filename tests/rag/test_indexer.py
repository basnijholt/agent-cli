"""Tests for RAG indexer."""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from watchfiles import Change

from agent_cli.rag import indexer


@pytest.mark.asyncio
async def test_watch_docs(tmp_path: Path) -> None:
    """Test watching docs folder."""
    mock_collection = MagicMock()
    docs_folder = tmp_path / "docs"
    docs_folder.mkdir()
    file_hashes: dict[str, str] = {}

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

    with (
        patch("agent_cli.rag.indexer.awatch", side_effect=mock_awatch_gen),
        patch("agent_cli.rag.indexer.index_file") as mock_index,
        patch("agent_cli.rag.indexer.remove_file") as mock_remove,
    ):
        await indexer.watch_docs(mock_collection, docs_folder, file_hashes)

        # Check calls
        assert mock_index.call_count == 2  # added and modified
        assert mock_remove.call_count == 1  # deleted


@pytest.mark.asyncio
async def test_watch_docs_ignore_dotfiles(tmp_path: Path) -> None:
    """Test ignoring dotfiles."""
    mock_collection = MagicMock()
    docs_folder = tmp_path / "docs"
    docs_folder.mkdir()
    file_hashes: dict[str, str] = {}

    changes = {
        (Change.added, str(docs_folder / ".hidden.txt")),
        (Change.added, str(docs_folder / "sub/.hidden")),
    }

    async def mock_awatch_gen(
        *_args: Any,
        **_kwargs: Any,
    ) -> AsyncGenerator[set[tuple[Change, str]], None]:
        yield changes

    with (
        patch("agent_cli.rag.indexer.awatch", side_effect=mock_awatch_gen),
        patch("agent_cli.rag.indexer.index_file") as mock_index,
    ):
        await indexer.watch_docs(mock_collection, docs_folder, file_hashes)

        mock_index.assert_not_called()
