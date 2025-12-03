"""Tests for the memory add CLI command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from agent_cli.agents.memory.add import _parse_memories, _strip_list_prefix
from agent_cli.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


# --- Tests for _strip_list_prefix helper ---


def test_strip_list_prefix_dash() -> None:
    """Test stripping dash prefix."""
    assert _strip_list_prefix("- User likes Python") == "User likes Python"


def test_strip_list_prefix_asterisk() -> None:
    """Test stripping asterisk prefix."""
    assert _strip_list_prefix("* User likes Python") == "User likes Python"


def test_strip_list_prefix_plus() -> None:
    """Test stripping plus prefix."""
    assert _strip_list_prefix("+ User likes Python") == "User likes Python"


def test_strip_list_prefix_numbered() -> None:
    """Test stripping numbered list prefixes."""
    assert _strip_list_prefix("1. User likes Python") == "User likes Python"
    assert _strip_list_prefix("10. User likes Python") == "User likes Python"
    assert _strip_list_prefix("99. User likes Python") == "User likes Python"


def test_strip_list_prefix_no_prefix() -> None:
    """Test that lines without prefix are unchanged."""
    assert _strip_list_prefix("User likes Python") == "User likes Python"


def test_strip_list_prefix_preserves_internal_dashes() -> None:
    """Test that internal dashes are preserved."""
    assert _strip_list_prefix("- User likes Python - a lot") == "User likes Python - a lot"


# --- Tests for _parse_memories function ---


def test_parse_memories_from_arguments() -> None:
    """Test parsing memories from command line arguments."""
    result = _parse_memories(["fact1", "fact2"], None, "default")
    assert result == [("fact1", "default"), ("fact2", "default")]


def test_parse_memories_from_plain_text_file(tmp_path: Path) -> None:
    """Test parsing memories from plain text file."""
    file = tmp_path / "memories.txt"
    file.write_text("fact1\nfact2\nfact3")
    result = _parse_memories([], file, "default")
    assert result == [("fact1", "default"), ("fact2", "default"), ("fact3", "default")]


def test_parse_memories_from_markdown_bullet_list(tmp_path: Path) -> None:
    """Test parsing memories from markdown bullet list."""
    file = tmp_path / "memories.md"
    file.write_text("- User likes Python\n- User lives in Amsterdam\n* User prefers vim")
    result = _parse_memories([], file, "default")
    assert result == [
        ("User likes Python", "default"),
        ("User lives in Amsterdam", "default"),
        ("User prefers vim", "default"),
    ]


def test_parse_memories_from_numbered_list(tmp_path: Path) -> None:
    """Test parsing memories from numbered list."""
    file = tmp_path / "memories.md"
    file.write_text("1. First fact\n2. Second fact\n3. Third fact")
    result = _parse_memories([], file, "default")
    assert result == [
        ("First fact", "default"),
        ("Second fact", "default"),
        ("Third fact", "default"),
    ]


def test_parse_memories_from_json_array(tmp_path: Path) -> None:
    """Test parsing memories from JSON array."""
    file = tmp_path / "memories.json"
    file.write_text('["fact1", "fact2"]')
    result = _parse_memories([], file, "default")
    assert result == [("fact1", "default"), ("fact2", "default")]


def test_parse_memories_from_json_object_with_memories_key(tmp_path: Path) -> None:
    """Test parsing memories from JSON object with 'memories' key."""
    file = tmp_path / "memories.json"
    file.write_text('{"memories": ["fact1", "fact2"]}')
    result = _parse_memories([], file, "default")
    assert result == [("fact1", "default"), ("fact2", "default")]


def test_parse_memories_from_json_with_conversation_id(tmp_path: Path) -> None:
    """Test parsing memories from JSON with per-item conversation IDs."""
    file = tmp_path / "memories.json"
    data = [{"content": "fact1", "conversation_id": "work"}, "fact2"]
    file.write_text(json.dumps(data))
    result = _parse_memories([], file, "default")
    assert result == [("fact1", "work"), ("fact2", "default")]


def test_parse_memories_skips_empty_lines(tmp_path: Path) -> None:
    """Test that empty lines are skipped."""
    file = tmp_path / "memories.txt"
    file.write_text("fact1\n\n\nfact2\n")
    result = _parse_memories([], file, "default")
    assert result == [("fact1", "default"), ("fact2", "default")]


def test_parse_memories_combines_file_and_arguments(tmp_path: Path) -> None:
    """Test combining file and argument memories."""
    file = tmp_path / "memories.txt"
    file.write_text("file_fact")
    result = _parse_memories(["arg_fact"], file, "default")
    assert result == [("file_fact", "default"), ("arg_fact", "default")]


# --- Tests for the memory add CLI command ---


def test_memory_add_help() -> None:
    """Test that help output is correct."""
    result = runner.invoke(app, ["memory", "add", "--help"])
    assert result.exit_code == 0
    assert "Add memories directly without LLM extraction" in result.stdout


def test_memory_add_single_memory(tmp_path: Path) -> None:
    """Test adding a single memory."""
    memory_path = tmp_path / "memory_db"
    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "User likes Python",
            "--memory-path",
            str(memory_path),
            "--no-git-versioning",
        ],
    )
    assert result.exit_code == 0
    assert "Added 1 memories" in result.stdout
    assert "User likes Python" in result.stdout

    # Verify file was created
    entries_dir = memory_path / "entries" / "default" / "facts"
    assert entries_dir.exists()
    files = list(entries_dir.glob("*.md"))
    assert len(files) == 1


def test_memory_add_multiple_memories(tmp_path: Path) -> None:
    """Test adding multiple memories."""
    memory_path = tmp_path / "memory_db"
    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "Fact one",
            "Fact two",
            "Fact three",
            "--memory-path",
            str(memory_path),
            "--no-git-versioning",
        ],
    )
    assert result.exit_code == 0
    assert "Added 3 memories" in result.stdout


def test_memory_add_from_file(tmp_path: Path) -> None:
    """Test adding memories from a file."""
    memory_path = tmp_path / "memory_db"
    input_file = tmp_path / "memories.md"
    input_file.write_text("- User likes coffee\n- User lives in Amsterdam")

    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "-f",
            str(input_file),
            "--memory-path",
            str(memory_path),
            "--no-git-versioning",
        ],
    )
    assert result.exit_code == 0
    assert "Added 2 memories" in result.stdout
    assert "User likes coffee" in result.stdout
    assert "User lives in Amsterdam" in result.stdout


def test_memory_add_with_conversation_id(tmp_path: Path) -> None:
    """Test adding memory with specific conversation ID."""
    memory_path = tmp_path / "memory_db"
    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "Work related fact",
            "-c",
            "work",
            "--memory-path",
            str(memory_path),
            "--no-git-versioning",
        ],
    )
    assert result.exit_code == 0

    # Verify file was created in correct conversation folder
    entries_dir = memory_path / "entries" / "work" / "facts"
    assert entries_dir.exists()
    files = list(entries_dir.glob("*.md"))
    assert len(files) == 1


def test_memory_add_no_memories_error(tmp_path: Path) -> None:
    """Test error when no memories provided."""
    memory_path = tmp_path / "memory_db"
    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--memory-path",
            str(memory_path),
            "--no-git-versioning",
        ],
    )
    assert result.exit_code == 1
    assert "No memories provided" in result.stdout


def test_memory_add_quiet_mode(tmp_path: Path) -> None:
    """Test quiet mode suppresses output."""
    memory_path = tmp_path / "memory_db"
    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "Silent fact",
            "--memory-path",
            str(memory_path),
            "--no-git-versioning",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == ""


def test_parse_memories_fallback_invalid_json(tmp_path: Path) -> None:
    """Test that text starting with brackets but invalid JSON falls back to plain text."""
    file = tmp_path / "memories.txt"
    # Starts with [ but is not a JSON list
    file.write_text("[Important] User likes Rust\n[Todo] Buy milk")
    result = _parse_memories([], file, "default")
    assert result == [
        ("[Important] User likes Rust", "default"),
        ("[Todo] Buy milk", "default"),
    ]


def test_parse_memories_fallback_invalid_json_object(tmp_path: Path) -> None:
    """Test that text starting with curly brace but invalid JSON falls back."""
    file = tmp_path / "memories.txt"
    # Starts with { but is not JSON
    file.write_text("{Tag} User likes Go")
    result = _parse_memories([], file, "default")
    assert result == [("{Tag} User likes Go", "default")]
