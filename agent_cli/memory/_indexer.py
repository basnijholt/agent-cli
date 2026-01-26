"""File watcher and indexing for file-backed memories."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agent_cli.core.watch import watch_directory
from agent_cli.memory._files import (
    _DELETED_DIRNAME,
    MemoryFileRecord,
    ensure_store_dirs,
    load_memory_files,
    load_snapshot,
    read_memory_file,
    write_snapshot,
)
from agent_cli.memory._store import delete_entries, upsert_memories

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection
    from watchfiles import Change

LOGGER = logging.getLogger(__name__)


@dataclass
class MemoryIndex:
    """In-memory view of memory files plus a JSON snapshot on disk."""

    entries: dict[str, MemoryFileRecord] = field(default_factory=dict)
    snapshot_path: Path | None = None

    @classmethod
    def from_snapshot(cls, snapshot_path: Path) -> MemoryIndex:
        """Restore index state from a snapshot file if present."""
        return cls(entries=load_snapshot(snapshot_path), snapshot_path=snapshot_path)

    def replace(self, records: list[MemoryFileRecord]) -> None:
        """Replace the in-memory index with the given records."""
        self.entries = {rec.id: rec for rec in records}
        self._persist()

    def upsert(self, record: MemoryFileRecord) -> None:
        """Insert or update a record and persist the snapshot."""
        self.entries[record.id] = record
        self._persist()

    def remove(self, doc_id: str) -> None:
        """Remove a record by id and persist the snapshot."""
        self.entries.pop(doc_id, None)
        self._persist()

    def find_id_by_path(self, path: Path) -> str | None:
        """Find a record id by its file path, if present."""
        for doc_id, record in self.entries.items():
            if record.path == path:
                return doc_id
        return None

    def _persist(self) -> None:
        if self.snapshot_path:
            write_snapshot(self.snapshot_path, self.entries.values())


def initial_index(collection: Collection, root: Path, *, index: MemoryIndex) -> None:
    """Load memory files, reconcile against snapshot, and index into Chroma."""
    entries_dir, snapshot_path = ensure_store_dirs(root)
    if index.snapshot_path is None:
        index.snapshot_path = snapshot_path

    records = load_memory_files(root)
    current_ids = {rec.id for rec in records}

    # Remove stale docs that were present in last snapshot but missing now
    stale_ids = set(index.entries) - current_ids
    if stale_ids:
        LOGGER.info("Removing %d stale memory docs from index", len(stale_ids))
        delete_entries(collection, list(stale_ids))

    if records:
        ids = [rec.id for rec in records]
        docs = [rec.content for rec in records]
        metas = [rec.metadata for rec in records]
        upsert_memories(collection, ids=ids, contents=docs, metadatas=metas)
        LOGGER.info("Indexed %d memory docs from %s", len(records), entries_dir)
    else:
        LOGGER.info("No memory files found in %s", entries_dir)

    index.replace(records)


async def watch_memory_store(collection: Collection, root: Path, *, index: MemoryIndex) -> None:
    """Watch the memory entries folder and keep Chroma in sync."""
    entries_dir, snapshot_path = ensure_store_dirs(root)
    if index.snapshot_path is None:
        index.snapshot_path = snapshot_path

    LOGGER.info("📁 Watching memory store: %s", entries_dir)
    await watch_directory(
        entries_dir,
        lambda change, path: _handle_change(change, path, collection, index),
    )


def _handle_change(change: Change, path: Path, collection: Collection, index: MemoryIndex) -> None:
    from watchfiles import Change  # noqa: PLC0415

    if path.suffix == ".tmp":
        return

    if _DELETED_DIRNAME in path.parts:
        return

    if change == Change.deleted:
        doc_id = index.find_id_by_path(path)
        if not doc_id:
            # Fallback: try to parse ID from filename (timestamp__uuid.md)
            parts = path.stem.split("__")
            doc_id = parts[-1] if len(parts) > 1 else path.stem

        LOGGER.info("[deleted] %s", path.name)
        delete_entries(collection, [doc_id])
        index.remove(doc_id)
        return

    if change in {Change.added, Change.modified}:
        action = "added" if change == Change.added else "modified"
        LOGGER.info("[%s] %s", action, path.name)
        record = read_memory_file(path)
        if not record:
            return
        upsert_memories(
            collection,
            ids=[record.id],
            contents=[record.content],
            metadatas=[record.metadata],
        )
        index.upsert(record)
