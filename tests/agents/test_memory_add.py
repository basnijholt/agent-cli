"""Tests for the memory add CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agent_cli.agents.memory.add import _parse_memories, _strip_list_prefix
from agent_cli.cli import app

runner = CliRunner()


class TestStripListPrefix:
    """Tests for _strip_list_prefix helper."""

    def test_dash_prefix(self) -> None:
        assert _strip_list_prefix("- User likes Python") == "User likes Python"

    def test_asterisk_prefix(self) -> None:
        assert _strip_list_prefix("* User likes Python") == "User likes Python"

    def test_plus_prefix(self) -> None:
        assert _strip_list_prefix("+ User likes Python") == "User likes Python"

    def test_numbered_prefix(self) -> None:
        assert _strip_list_prefix("1. User likes Python") == "User likes Python"
        assert _strip_list_prefix("10. User likes Python") == "User likes Python"
        assert _strip_list_prefix("99. User likes Python") == "User likes Python"

    def test_no_prefix(self) -> None:
        assert _strip_list_prefix("User likes Python") == "User likes Python"

    def test_preserves_internal_dashes(self) -> None:
        assert _strip_list_prefix("- User likes Python - a lot") == "User likes Python - a lot"


class TestParseMemories:
    """Tests for _parse_memories function."""

    def test_from_arguments(self) -> None:
        result = _parse_memories(["fact1", "fact2"], None, "default")
        assert result == [("fact1", "default"), ("fact2", "default")]

    def test_from_plain_text_file(self, tmp_path: Path) -> None:
        file = tmp_path / "memories.txt"
        file.write_text("fact1\nfact2\nfact3")
        result = _parse_memories([], file, "default")
        assert result == [("fact1", "default"), ("fact2", "default"), ("fact3", "default")]

    def test_from_markdown_bullet_list(self, tmp_path: Path) -> None:
        file = tmp_path / "memories.md"
        file.write_text("- User likes Python\n- User lives in Amsterdam\n* User prefers vim")
        result = _parse_memories([], file, "default")
        assert result == [
            ("User likes Python", "default"),
            ("User lives in Amsterdam", "default"),
            ("User prefers vim", "default"),
        ]

    def test_from_numbered_list(self, tmp_path: Path) -> None:
        file = tmp_path / "memories.md"
        file.write_text("1. First fact\n2. Second fact\n3. Third fact")
        result = _parse_memories([], file, "default")
        assert result == [
            ("First fact", "default"),
            ("Second fact", "default"),
            ("Third fact", "default"),
        ]

    def test_from_json_array(self, tmp_path: Path) -> None:
        file = tmp_path / "memories.json"
        file.write_text('["fact1", "fact2"]')
        result = _parse_memories([], file, "default")
        assert result == [("fact1", "default"), ("fact2", "default")]

    def test_from_json_object_with_memories_key(self, tmp_path: Path) -> None:
        file = tmp_path / "memories.json"
        file.write_text('{"memories": ["fact1", "fact2"]}')
        result = _parse_memories([], file, "default")
        assert result == [("fact1", "default"), ("fact2", "default")]

    def test_from_json_with_conversation_id(self, tmp_path: Path) -> None:
        file = tmp_path / "memories.json"
        data = [{"content": "fact1", "conversation_id": "work"}, "fact2"]
        file.write_text(json.dumps(data))
        result = _parse_memories([], file, "default")
        assert result == [("fact1", "work"), ("fact2", "default")]

    def test_skips_empty_lines(self, tmp_path: Path) -> None:
        file = tmp_path / "memories.txt"
        file.write_text("fact1\n\n\nfact2\n")
        result = _parse_memories([], file, "default")
        assert result == [("fact1", "default"), ("fact2", "default")]

    def test_combines_file_and_arguments(self, tmp_path: Path) -> None:
        file = tmp_path / "memories.txt"
        file.write_text("file_fact")
        result = _parse_memories(["arg_fact"], file, "default")
        assert result == [("file_fact", "default"), ("arg_fact", "default")]


class TestMemoryAddCLI:
    """Tests for the memory add CLI command."""

    def test_help(self) -> None:
        result = runner.invoke(app, ["memory", "add", "--help"])
        assert result.exit_code == 0
        assert "Add memories directly without LLM extraction" in result.stdout

    def test_add_single_memory(self, tmp_path: Path) -> None:
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

    def test_add_multiple_memories(self, tmp_path: Path) -> None:
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

    def test_add_from_file(self, tmp_path: Path) -> None:
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

    def test_add_with_conversation_id(self, tmp_path: Path) -> None:
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

    def test_no_memories_error(self, tmp_path: Path) -> None:
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

    def test_quiet_mode(self, tmp_path: Path) -> None:
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
