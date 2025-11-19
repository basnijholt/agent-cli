"""File watcher and indexing logic."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from agent_cli.rag.engine import index_file, remove_file

if TYPE_CHECKING:
    from chromadb import Collection

logger = logging.getLogger("agent_cli.rag.indexer")


class RAGEventHandler(FileSystemEventHandler):
    """Watch for file system events and trigger indexing."""

    def __init__(
        self,
        collection: Collection,
        docs_folder: Path,
        file_hashes: dict[str, str],
    ) -> None:
        """Initialize the watcher."""
        self.collection = collection
        self.docs_folder = docs_folder
        self.file_hashes = file_hashes
        self.processing: set[str] = set()
        self._lock = threading.Lock()

    def on_created(self, event: Any) -> None:
        """Handle file creation."""
        if not event.is_directory:
            self._process_file(event.src_path, "created")

    def on_modified(self, event: Any) -> None:
        """Handle file modification."""
        if not event.is_directory:
            self._process_file(event.src_path, "modified")

    def on_deleted(self, event: Any) -> None:
        """Handle file deletion."""
        if not event.is_directory:
            self._remove_file(event.src_path)

    def on_moved(self, event: Any) -> None:
        """Handle file move."""
        if not event.is_directory:
            self._remove_file(event.src_path)
            self._process_file(event.dest_path, "moved")

    def _process_file(self, file_path: str, action: str) -> None:
        path = Path(file_path)

        # Ignore hidden files or temporary files
        if path.name.startswith(".") or path.name.endswith("~"):
            return

        with self._lock:
            if str(path) in self.processing:
                return
            self.processing.add(str(path))

        # Run in a separate thread to not block the observer
        threading.Thread(
            target=self._index_worker,
            args=(path, action),
            daemon=True,
        ).start()

    def _index_worker(self, path: Path, action: str) -> None:
        try:
            # Small delay to ensure file write is complete
            time.sleep(0.5)
            if path.exists():
                logger.info("[%s] Indexing: %s", action, path.name)
                index_file(self.collection, self.docs_folder, path, self.file_hashes)
        except Exception:
            logger.exception("Failed to index %s", path.name)
        finally:
            with self._lock:
                self.processing.discard(str(path))

    def _remove_file(self, file_path: str) -> None:
        path = Path(file_path)
        # Ignore hidden files
        if path.name.startswith("."):
            return

        logger.info("[deleted] Removing from index: %s", path.name)
        remove_file(self.collection, self.docs_folder, path, self.file_hashes)


def start_watcher(
    collection: Collection,
    docs_folder: Path,
    file_hashes: dict[str, str],
) -> Observer:
    """Start watching the docs folder."""
    event_handler = RAGEventHandler(collection, docs_folder, file_hashes)
    observer = Observer()
    observer.schedule(event_handler, str(docs_folder), recursive=True)
    observer.start()
    logger.info("📁 Watching folder: %s", docs_folder)
    return observer
