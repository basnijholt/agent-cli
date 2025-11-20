"""Tests for file-backed memory helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_cli.memory import files as mem_files
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
        salience=0.8,
        tags=["bike", "name"],
    )

    loaded = mem_files.read_memory_file(record.path)
    assert loaded is not None
    assert loaded.content == "fact about bikes"
    assert loaded.metadata.conversation_id == "conv-1"
    assert loaded.metadata.tags == ["bike", "name"]


def test_snapshot_round_trip(tmp_path: Path) -> None:
    """Snapshot JSON stores and restores memory records."""
    meta = MemoryMetadata(
        conversation_id="c1",
        role="memory",
        created_at="now",
        salience=None,
        tags=["x"],
    )
    rec = mem_files.MemoryFileRecord(id="1", path=tmp_path / "p.md", metadata=meta, content="hi")
    snapshot = tmp_path / "snap.json"

    mem_files.write_snapshot(snapshot, [rec])
    loaded = mem_files.load_snapshot(snapshot)

    assert "1" in loaded
    assert loaded["1"].metadata.tags == ["x"]
    assert loaded["1"].content == "hi"
