"""Tests for file-backed memory helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_cli.memory import _files as mem_files
from agent_cli.memory.models import MemoryMetadata

if TYPE_CHECKING:
    from pathlib import Path


def test_write_and_read_memory_file_round_trip(tmp_path: Path) -> None:
    """Writes a memory file and reads it back with metadata intact."""
    record = mem_files.write_memory_file(
        tmp_path,
        conversation_id="conv-1",
        role="memory",
        created_at="2025-01-01T00:00:00Z",
        content="fact about bikes",
    )

    loaded = mem_files.read_memory_file(record.path)
    assert loaded is not None
    assert loaded.content == "fact about bikes"
    assert loaded.metadata.conversation_id == "conv-1"
    assert "facts" in loaded.path.parts


def test_snapshot_round_trip(tmp_path: Path) -> None:
    """Snapshot JSON stores and restores memory records."""
    meta = MemoryMetadata(
        conversation_id="c1",
        role="memory",
        created_at="now",
    )
    rec = mem_files.MemoryFileRecord(id="1", path=tmp_path / "p.md", metadata=meta, content="hi")
    snapshot = tmp_path / "snap.json"

    mem_files.write_snapshot(snapshot, [rec])
    loaded = mem_files.load_snapshot(snapshot)

    assert "1" in loaded
    assert loaded["1"].content == "hi"


def test_load_memory_files_skips_invalid(tmp_path: Path) -> None:
    """Invalid files without front matter should be ignored."""
    entries_dir = tmp_path / "entries" / "default"
    entries_dir.mkdir(parents=True, exist_ok=True)
    bad_file = entries_dir / "bad.md"
    bad_file.write_text("no front matter here", encoding="utf-8")

    records = mem_files.load_memory_files(tmp_path)
    assert records == []
