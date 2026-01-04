"""Tests for the memory tools in _tools.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_cli._tools import (
    MemoryTools,
    _format_memory_content,
    create_memory_tools,
    tools,
)
from agent_cli.agents.chat import (
    _get_conversation_id,
    _maybe_extract_memories,
    _maybe_init_memory,
)
from agent_cli.config import History, Memory, OpenAILLM

# --- Tests for _format_memory_content ---


def test_format_memory_content_basic() -> None:
    """Test basic memory content formatting."""
    result = _format_memory_content("User likes Python", "preferences", "")
    assert result == "[preferences] User likes Python"


def test_format_memory_content_with_tags() -> None:
    """Test memory content formatting with tags."""
    result = _format_memory_content("User likes Python", "preferences", "programming, languages")
    assert result == "[preferences] User likes Python (tags: programming, languages)"


def test_format_memory_content_empty_category() -> None:
    """Test memory content formatting with empty category."""
    result = _format_memory_content("Some content", "", "")
    assert result == "[] Some content"


# --- Tests for MemoryTools._check ---


def test_memory_tools_check_with_no_client() -> None:
    """Test that _check returns error when client is None."""
    mt = MemoryTools(None, "test_conversation")
    error = mt._check()
    assert error is not None
    assert "Memory system not initialized" in error
    assert "pip install 'agent-cli[memory]'" in error


def test_memory_tools_check_with_client() -> None:
    """Test that _check returns None when client exists."""
    mock_client = MagicMock()
    mt = MemoryTools(mock_client, "test_conversation")
    error = mt._check()
    assert error is None


# --- Tests for MemoryTools.add_memory ---


@pytest.mark.asyncio
async def test_add_memory_without_client() -> None:
    """Test add_memory returns error when no client."""
    mt = MemoryTools(None, "test")
    result = await mt.add_memory("content", "category", "tags")
    assert "Error: Memory system not initialized" in result


@pytest.mark.asyncio
async def test_add_memory_success() -> None:
    """Test successful memory addition."""
    mock_client = MagicMock()
    mock_client.add = AsyncMock()

    mt = MemoryTools(mock_client, "test_conversation")
    result = await mt.add_memory("User likes coffee", "preferences", "food")

    assert result == "Memory added successfully."
    mock_client.add.assert_called_once_with(
        "[preferences] User likes coffee (tags: food)",
        conversation_id="test_conversation",
    )


@pytest.mark.asyncio
async def test_add_memory_exception() -> None:
    """Test add_memory handles exceptions."""
    mock_client = MagicMock()
    mock_client.add = AsyncMock(side_effect=RuntimeError("Database error"))

    mt = MemoryTools(mock_client, "test")
    result = await mt.add_memory("content", "category", "tags")

    assert "Error adding memory" in result
    assert "Database error" in result


# --- Tests for MemoryTools.search_memory ---


@pytest.mark.asyncio
async def test_search_memory_without_client() -> None:
    """Test search_memory returns error when no client."""
    mt = MemoryTools(None, "test")
    result = await mt.search_memory("query")
    assert "Error: Memory system not initialized" in result


@pytest.mark.asyncio
async def test_search_memory_no_results() -> None:
    """Test search_memory with no matching results."""
    mock_retrieval = MagicMock()
    mock_retrieval.entries = []

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=mock_retrieval)

    mt = MemoryTools(mock_client, "test")
    result = await mt.search_memory("nonexistent")

    assert "No memories found matching 'nonexistent'" in result


@pytest.mark.asyncio
async def test_search_memory_with_results() -> None:
    """Test search_memory returns formatted results."""
    # Create mock entries
    entry1 = MagicMock()
    entry1.content = "User likes Python"
    entry1.score = 0.95

    entry2 = MagicMock()
    entry2.content = "User prefers dark mode"
    entry2.score = 0.87

    mock_retrieval = MagicMock()
    mock_retrieval.entries = [entry1, entry2]

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=mock_retrieval)

    mt = MemoryTools(mock_client, "test")
    result = await mt.search_memory("preferences")

    assert "User likes Python" in result
    assert "User prefers dark mode" in result
    assert "relevance: 0.95" in result
    assert "relevance: 0.87" in result


@pytest.mark.asyncio
async def test_search_memory_with_category() -> None:
    """Test search_memory includes category in query."""
    mock_retrieval = MagicMock()
    mock_retrieval.entries = []

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=mock_retrieval)

    mt = MemoryTools(mock_client, "test_conv")
    await mt.search_memory("coffee", category="preferences")

    # Verify category is prepended to the query
    mock_client.search.assert_called_once_with(
        "preferences coffee",
        conversation_id="test_conv",
    )


@pytest.mark.asyncio
async def test_search_memory_exception() -> None:
    """Test search_memory handles exceptions."""
    mock_client = MagicMock()
    mock_client.search = AsyncMock(side_effect=RuntimeError("Search failed"))

    mt = MemoryTools(mock_client, "test")
    result = await mt.search_memory("query")

    assert "Error searching memory" in result
    assert "Search failed" in result


# --- Tests for MemoryTools.list_all_memories ---


def test_list_all_memories_without_client() -> None:
    """Test list_all_memories returns error when no client."""
    mt = MemoryTools(None, "test")
    result = mt.list_all_memories()
    assert "Error: Memory system not initialized" in result


def test_list_all_memories_empty() -> None:
    """Test list_all_memories with no stored memories."""
    mock_client = MagicMock()
    mock_client.list_all = MagicMock(return_value=[])

    mt = MemoryTools(mock_client, "test")
    result = mt.list_all_memories()

    assert result == "No memories stored yet."


def test_list_all_memories_with_entries() -> None:
    """Test list_all_memories returns formatted list."""
    entries = [
        {"content": "User likes Python", "role": "memory", "created_at": "2024-01-01T10:00:00"},
        {
            "content": "User lives in Amsterdam",
            "role": "memory",
            "created_at": "2024-01-02T12:00:00",
        },
    ]
    mock_client = MagicMock()
    mock_client.list_all = MagicMock(return_value=entries)

    mt = MemoryTools(mock_client, "test")
    result = mt.list_all_memories()

    assert "Showing 2 of 2 total memories" in result
    assert "User likes Python" in result
    assert "User lives in Amsterdam" in result
    assert "[memory]" in result


def test_list_all_memories_with_limit() -> None:
    """Test list_all_memories respects limit parameter."""
    entries = [
        {"content": f"Memory {i}", "role": "memory", "created_at": "2024-01-01"} for i in range(5)
    ]
    mock_client = MagicMock()
    mock_client.list_all = MagicMock(return_value=entries)

    mt = MemoryTools(mock_client, "test")
    result = mt.list_all_memories(limit=3)

    assert "Showing 3 of 5 total memories" in result
    assert "... and 2 more memories" in result


def test_list_all_memories_exception() -> None:
    """Test list_all_memories handles exceptions."""
    mock_client = MagicMock()
    mock_client.list_all = MagicMock(side_effect=RuntimeError("List failed"))

    mt = MemoryTools(mock_client, "test")
    result = mt.list_all_memories()

    assert "Error listing memories" in result
    assert "List failed" in result


# --- Tests for create_memory_tools ---


def test_create_memory_tools_returns_list() -> None:
    """Test create_memory_tools returns a list of Tool objects."""
    mock_client = MagicMock()
    result = create_memory_tools(mock_client, "test")

    assert isinstance(result, list)
    assert len(result) == 3  # add_memory, search_memory, list_all_memories


def test_create_memory_tools_with_none_client() -> None:
    """Test create_memory_tools works with None client."""
    result = create_memory_tools(None, "test")

    assert isinstance(result, list)
    assert len(result) == 3


# --- Tests for tools function ---


def test_tools_returns_all_expected_tools() -> None:
    """Test tools function returns all expected tools."""
    result = tools(None, "test")

    assert isinstance(result, list)
    # Should have: read_file, execute_code, 3 memory tools, duckduckgo_search
    assert len(result) == 6


def test_tools_with_memory_client() -> None:
    """Test tools function works with a memory client."""
    mock_client = MagicMock()
    result = tools(mock_client, "conversation_123")

    assert isinstance(result, list)
    assert len(result) == 6


# --- Tests for chat.py integration functions ---


def test_get_conversation_id_with_history_dir() -> None:
    """Test _get_conversation_id generates stable ID from history dir."""
    history_cfg = History(history_dir=Path("/home/user/.chat-history"))
    result = _get_conversation_id(history_cfg)

    # Should be a 12-character hex string
    assert len(result) == 12
    assert all(c in "0123456789abcdef" for c in result)


def test_get_conversation_id_without_history_dir() -> None:
    """Test _get_conversation_id returns 'default' when no history dir."""
    history_cfg = History(history_dir=None)
    result = _get_conversation_id(history_cfg)

    assert result == "default"


def test_get_conversation_id_is_stable() -> None:
    """Test _get_conversation_id produces same ID for same path."""
    history_cfg1 = History(history_dir=Path("/some/path"))
    history_cfg2 = History(history_dir=Path("/some/path"))

    assert _get_conversation_id(history_cfg1) == _get_conversation_id(history_cfg2)


@pytest.mark.asyncio
async def test_maybe_extract_memories_off_mode() -> None:
    """Test _maybe_extract_memories does nothing when mode is not 'auto'."""
    memory_cfg = Memory(mode="tools")  # Not 'auto'
    mock_client = MagicMock()
    mock_client.extract_from_turn = AsyncMock()

    await _maybe_extract_memories(
        memory_cfg=memory_cfg,
        memory_client=mock_client,
        instruction="test",
        response_text="response",
        conversation_id="test",
        model="gpt-4",
        quiet=True,
    )

    # Should not call extract_from_turn when mode is not 'auto'
    mock_client.extract_from_turn.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_extract_memories_auto_mode() -> None:
    """Test _maybe_extract_memories extracts when mode is 'auto'."""
    memory_cfg = Memory(mode="auto")
    mock_client = MagicMock()
    mock_client.extract_from_turn = AsyncMock()

    await _maybe_extract_memories(
        memory_cfg=memory_cfg,
        memory_client=mock_client,
        instruction="Hello world",
        response_text="Hi there!",
        conversation_id="conv123",
        model="gpt-4",
        quiet=True,
    )

    mock_client.extract_from_turn.assert_called_once_with(
        user_message="Hello world",
        assistant_message="Hi there!",
        conversation_id="conv123",
        model="gpt-4",
    )


@pytest.mark.asyncio
async def test_maybe_extract_memories_handles_exception() -> None:
    """Test _maybe_extract_memories handles exceptions gracefully."""
    memory_cfg = Memory(mode="auto")
    mock_client = MagicMock()
    mock_client.extract_from_turn = AsyncMock(side_effect=RuntimeError("Extraction failed"))

    # Should not raise, just log warning
    await _maybe_extract_memories(
        memory_cfg=memory_cfg,
        memory_client=mock_client,
        instruction="test",
        response_text="response",
        conversation_id="test",
        model="gpt-4",
        quiet=True,
    )


@pytest.mark.asyncio
async def test_maybe_extract_memories_no_client() -> None:
    """Test _maybe_extract_memories does nothing when client is None."""
    memory_cfg = Memory(mode="auto")

    # Should not raise even with None client
    await _maybe_extract_memories(
        memory_cfg=memory_cfg,
        memory_client=None,
        instruction="test",
        response_text="response",
        conversation_id="test",
        model="gpt-4",
        quiet=True,
    )


def test_maybe_init_memory_off_mode() -> None:
    """Test _maybe_init_memory returns None when mode is 'off'."""
    memory_cfg = Memory(mode="off")
    history_cfg = History()
    openai_cfg = OpenAILLM(llm_openai_model="gpt-4o-mini")

    result = _maybe_init_memory(memory_cfg, history_cfg, openai_cfg, quiet=True)
    assert result is None
