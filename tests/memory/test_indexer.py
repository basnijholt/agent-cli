"""Indexer and watcher tests for file-based memory."""

from __future__ import annotations

from typing import Any

from watchfiles import Change

from agent_cli.memory import _files as mem_files
from agent_cli.memory import _indexer


class _FakeCollection:
    def __init__(self) -> None:
        self.upserts: list[tuple[list[str], list[str], list[dict[str, Any]]]] = []
        self.deleted: list[list[str]] = []

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        self.upserts.append((ids, documents, metadatas))

    def delete(self, ids: list[str]) -> None:
        self.deleted.append(ids)


def test_initial_index_deletes_stale_and_indexes_current(tmp_path: Any) -> None:
    fake = _FakeCollection()
    idx = _indexer.MemoryIndex.from_snapshot(tmp_path / "memory_index.json")
    idx.entries["stale"] = mem_files.MemoryFileRecord(
        id="stale",
        path=tmp_path / "entries" / "default" / "stale.md",
        metadata=mem_files.MemoryMetadata(conversation_id="c", role="memory", created_at="now"),  # type: ignore[attr-defined]
        content="old",
    )

    rec = mem_files.write_memory_file(
        tmp_path,
        conversation_id="c",
        role="memory",
        created_at="now",
        content="fresh",
    )

    _indexer.initial_index(fake, tmp_path, index=idx)

    assert fake.deleted == [["stale"]]
    assert fake.upserts  # fresh file indexed
    assert rec.id in idx.entries


def test_handle_change_add_modify_delete(tmp_path: Any) -> None:
    fake = _FakeCollection()
    idx = _indexer.MemoryIndex(snapshot_path=None)

    rec = mem_files.write_memory_file(
        tmp_path,
        conversation_id="c",
        role="memory",
        created_at="now",
        content="hello",
    )

    _indexer._handle_change(Change.added, rec.path, fake, idx)
    assert fake.upserts
    assert rec.id in idx.entries

    _indexer._handle_change(Change.modified, rec.path, fake, idx)
    assert len(fake.upserts) >= 2

    _indexer._handle_change(Change.deleted, rec.path, fake, idx)
    assert fake.deleted
    assert rec.id not in idx.entries
