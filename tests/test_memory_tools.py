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


def test_add_and_search_memory(tmp_path: Path) -> None:
    """Test the add_memory and search_memory functions."""
    memory_file = tmp_path / "long_term_memory.json"
    with patch("agent_cli._tools._get_memory_file_path", return_value=memory_file):
        # Test searching in an empty memory
        assert "No memories found" in _tools.search_memory("test")

        # Test adding a memory
        result = _tools.add_memory("test content", "test_category", "tag1, tag2")
        assert "Memory added successfully with ID 1" in result

        # Test searching for the new memory
        search_result = _tools.search_memory("test content")
        assert "ID: 1" in search_result
        assert "Category: test_category" in search_result
        assert "Content: test content" in search_result
        assert "Tags: tag1, tag2" in search_result

        # Test searching with a category filter
        search_result_cat = _tools.search_memory("test", category="test_category")
        assert "ID: 1" in search_result_cat

        # Test searching with a non-matching category
        search_result_no_cat = _tools.search_memory("test", category="wrong_category")
        assert "No memories found" in search_result_no_cat


def test_update_memory(tmp_path: Path) -> None:
    """Test the update_memory function."""
    memory_file = tmp_path / "long_term_memory.json"
    with patch("agent_cli._tools._get_memory_file_path", return_value=memory_file):
        # Add a memory to work with
        _tools.add_memory("original content", "original_category", "original_tag")

        # Test updating a non-existent memory
        assert "not found" in _tools.update_memory(2, content="new")

        # Test updating the existing memory
        update_result = _tools.update_memory(1, content="new content", category="new_category")
        assert "updated successfully" in update_result

        # Verify the update
        search_result = _tools.search_memory("new content")
        assert "Category: new_category" in search_result


def test_list_all_and_categories(tmp_path: Path) -> None:
    """Test the list_all_memories and list_memory_categories functions."""
    memory_file = tmp_path / "long_term_memory.json"
    with patch("agent_cli._tools._get_memory_file_path", return_value=memory_file):
        # Test with no memories
        assert "No memories stored" in _tools.list_all_memories()
        assert "No memories found" in _tools.list_memory_categories()

        # Add some memories
        _tools.add_memory("content1", "cat1", "tag1")
        _tools.add_memory("content2", "cat2", "tag2")
        _tools.add_memory("content3", "cat1", "tag3")

        # Test list_all_memories
        list_all_result = _tools.list_all_memories()
        assert "Showing 3 of 3 total memories" in list_all_result
        assert "ID: 1" in list_all_result
        assert "ID: 2" in list_all_result
        assert "ID: 3" in list_all_result

        # Test list_memory_categories
        list_cat_result = _tools.list_memory_categories()
        assert "cat1: 2 memories" in list_cat_result
        assert "cat2: 1 memories" in list_cat_result
