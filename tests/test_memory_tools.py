"""Tests for the memory tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest  # noqa: TC002

from agent_cli import _tools


def test_get_memory_file_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test the _get_memory_file_path function."""
    # Test with AGENT_CLI_HISTORY_DIR set
    history_dir = tmp_path / "history"
    monkeypatch.setenv("AGENT_CLI_HISTORY_DIR", str(history_dir))
    path = _tools._get_memory_file_path()
    assert path == history_dir / "long_term_memory.json"

    # Test without AGENT_CLI_HISTORY_DIR set
    monkeypatch.delenv("AGENT_CLI_HISTORY_DIR", raising=False)
    path = _tools._get_memory_file_path()
    assert path == Path.home() / ".config" / "agent-cli" / "memory" / "long_term_memory.json"


def test_load_and_save_memories(tmp_path: Path) -> None:
    """Test the _load_memories and _save_memories functions."""
    memory_file = tmp_path / "long_term_memory.json"
    with patch("agent_cli._tools._get_memory_file_path", return_value=memory_file):
        # Test loading from a non-existent file
        memories = _tools._load_memories()
        assert memories == []

        # Test saving and then loading
        memories_to_save = [{"id": 1, "content": "test"}]
        _tools._save_memories(memories_to_save)

        loaded_memories = _tools._load_memories()
        assert loaded_memories == memories_to_save

        # Verify the file content
        with memory_file.open("r") as f:
            assert json.load(f) == memories_to_save
