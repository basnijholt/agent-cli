"""File watcher and indexing logic using watchfiles."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from watchfiles import Change

from agent_cli.core.watch import watch_directory
from agent_cli.rag.indexing import index_file, remove_file

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

LOGGER = logging.getLogger("agent_cli.rag.indexer")


async def watch_docs(
    collection: Collection,
    docs_folder: Path,
    file_hashes: dict[str, str],
) -> None:
    """Watch docs folder for changes and update index asynchronously."""
    LOGGER.info("📁 Watching folder: %s", docs_folder)

    await watch_directory(
        docs_folder,
        lambda change, path: _handle_change(change, path, collection, docs_folder, file_hashes),
    )


def _handle_change(
    change: Change,
    file_path: Path,
    collection: Collection,
    docs_folder: Path,
    file_hashes: dict[str, str],
) -> None:
    try:
        if change == Change.deleted:
            LOGGER.info("[deleted] Removing from index: %s", file_path.name)
            remove_file(collection, docs_folder, file_path, file_hashes)
            return
        if change in {Change.added, Change.modified} and file_path.is_file():
            action = "created" if change == Change.added else "modified"
            LOGGER.info("[%s] Indexing: %s", action, file_path.name)
            index_file(collection, docs_folder, file_path, file_hashes)
    except Exception:
        LOGGER.exception("Watcher handler failed for %s", file_path)
