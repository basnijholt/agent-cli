"""File watcher and indexing logic using watchfiles."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_cli.core.watch import watch_directory
from agent_cli.rag._indexing import index_file, remove_file
from agent_cli.rag._utils import should_ignore_path

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection
    from watchfiles import Change

LOGGER = logging.getLogger(__name__)


async def watch_docs(
    collection: Collection,
    docs_folder: Path,
    file_hashes: dict[str, str],
    file_mtimes: dict[str, float],
) -> None:
    """Watch docs folder for changes and update index asynchronously."""
    LOGGER.info("📁 Watching folder: %s", docs_folder)

    await watch_directory(
        docs_folder,
        lambda change, path: _handle_change(
            change,
            path,
            collection,
            docs_folder,
            file_hashes,
            file_mtimes,
        ),
        ignore_filter=should_ignore_path,
    )


def _handle_change(
    change: Change,
    file_path: Path,
    collection: Collection,
    docs_folder: Path,
    file_hashes: dict[str, str],
    file_mtimes: dict[str, float],
) -> None:
    from watchfiles import Change  # noqa: PLC0415

    try:
        if change == Change.deleted:
            LOGGER.info("[deleted] Removing from index: %s", file_path.name)
            remove_file(collection, docs_folder, file_path, file_hashes, file_mtimes)
            return
        if change in {Change.added, Change.modified} and file_path.is_file():
            action = "created" if change == Change.added else "modified"
            LOGGER.info("[%s] Indexing: %s", action, file_path.name)
            index_file(collection, docs_folder, file_path, file_hashes, file_mtimes)
    except (OSError, UnicodeDecodeError):
        LOGGER.warning("Watcher handler transient IO error for %s", file_path, exc_info=True)
    except Exception:
        LOGGER.exception("Watcher handler failed for %s", file_path)
        raise
