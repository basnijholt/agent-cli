"""Tests for SSE formatting helpers."""

import json

from agent_cli.core.sse import (
    extract_content_from_chunk,
    format_chunk,
    format_done,
    parse_chunk,
)


def test_format_chunk_with_content() -> None:
    """Test formatting a chunk with content."""
    result = format_chunk("test-id", "gpt-4", content="Hello")
    assert result.startswith("data: ")
    assert result.endswith("\n\n")

    data = json.loads(result[6:])
    assert data["id"] == "chatcmpl-test-id"
    assert data["object"] == "chat.completion.chunk"
    assert data["model"] == "gpt-4"
    assert data["choices"][0]["delta"]["content"] == "Hello"
    assert data["choices"][0]["finish_reason"] is None


def test_format_chunk_finish() -> None:
    """Test formatting a finish chunk."""
    result = format_chunk("test-id", "gpt-4", finish_reason="stop")
    data = json.loads(result[6:])

    assert data["choices"][0]["delta"] == {}
    assert data["choices"][0]["finish_reason"] == "stop"


def test_format_chunk_with_extra() -> None:
    """Test formatting a chunk with extra fields."""
    extra = {"rag_sources": [{"path": "test.md"}]}
    result = format_chunk("test-id", "gpt-4", finish_reason="stop", extra=extra)
    data = json.loads(result[6:])

    assert data["rag_sources"] == [{"path": "test.md"}]


def test_format_done() -> None:
    """Test formatting the done message."""
    assert format_done() == "data: [DONE]\n\n"


def test_parse_chunk_valid() -> None:
    """Test parsing a valid chunk."""
    line = 'data: {"choices": [{"delta": {"content": "Hi"}}]}'
    result = parse_chunk(line)

    assert result is not None
    assert result["choices"][0]["delta"]["content"] == "Hi"


def test_parse_chunk_done() -> None:
    """Test parsing the done message returns None."""
    assert parse_chunk("data: [DONE]") is None


def test_parse_chunk_invalid() -> None:
    """Test parsing invalid input returns None."""
    assert parse_chunk("not a data line") is None
    assert parse_chunk("data: {invalid json}") is None


def test_extract_content_from_chunk() -> None:
    """Test extracting content from a parsed chunk."""
    chunk = {"choices": [{"delta": {"content": "Hello"}}]}
    assert extract_content_from_chunk(chunk) == "Hello"

    # Empty delta
    chunk_empty: dict[str, list[dict[str, dict[str, str]]]] = {"choices": [{"delta": {}}]}
    assert extract_content_from_chunk(chunk_empty) == ""

    # Alternative text field
    chunk_text = {"choices": [{"delta": {"text": "World"}}]}
    assert extract_content_from_chunk(chunk_text) == "World"
