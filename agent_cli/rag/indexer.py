"""File watcher and indexing logic using watchfiles."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from watchfiles import Change, awatch

from agent_cli.rag.indexing import index_file, remove_file

if TYPE_CHECKING:
    from chromadb import Collection

logger = logging.getLogger("agent_cli.rag.indexer")


async def watch_docs(
    collection: Collection,
    docs_folder: Path,
    file_hashes: dict[str, str],
) -> None:
    """Watch docs folder for changes and update index asynchronously."""
    logger.info("📁 Watching folder: %s", docs_folder)

    loop = asyncio.get_running_loop()

    async for changes in awatch(docs_folder):
        for change_type, file_path_str in changes:
            file_path = Path(file_path_str)

            # Skip dotfiles/dirs if watchfiles doesn't catch all
            try:
                rel_path = file_path.relative_to(docs_folder)
                if any(part.startswith(".") for part in rel_path.parts):
                    continue
            except ValueError:
                if file_path.name.startswith("."):
                    continue

            if change_type == Change.deleted:
                # Offload blocking IO/DB operations to thread pool
                await loop.run_in_executor(
                    None,
                    _remove_file,
                    collection,
                    docs_folder,
                    file_path,
                    file_hashes,
                )
            elif (change_type in {Change.added, Change.modified}) and file_path.is_file():
                # Offload blocking hashing/chunking/DB ops to thread pool
                await loop.run_in_executor(
                    None,
                    _process_file,
                    collection,
                    docs_folder,
                    file_path,
                    file_hashes,
                    change_type,
                )


def _process_file(
    collection: Collection,
    docs_folder: Path,
    file_path: Path,
    file_hashes: dict[str, str],
    change_type: Change,
) -> None:
    action = "created" if change_type == Change.added else "modified"
    logger.info("[%s] Indexing: %s", action, file_path.name)
    index_file(collection, docs_folder, file_path, file_hashes)


def _remove_file(
    collection: Collection,
    docs_folder: Path,
    file_path: Path,
    file_hashes: dict[str, str],
) -> None:
    logger.info("[deleted] Removing from index: %s", file_path.name)
    remove_file(collection, docs_folder, file_path, file_hashes)
