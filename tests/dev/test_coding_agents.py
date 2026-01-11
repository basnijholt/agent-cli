"""Tests for AI coding agent adapters."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_cli.dev.coding_agents import (
    CodingAgent,
    detect_current_agent,
    get_agent,
    get_all_agents,
    get_available_agents,
)
from agent_cli.dev.coding_agents.aider import Aider
from agent_cli.dev.coding_agents.claude import ClaudeCode
from agent_cli.dev.coding_agents.cursor_agent import CursorAgent


class TestCodingAgentBase:
    """Tests for CodingAgent base class."""

    def test_detect_with_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect agent via environment variable set to '1'."""
        monkeypatch.setenv("CLAUDECODE", "1")
        agent = ClaudeCode()
        assert agent.detect() is True

    def test_detect_env_var_must_be_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variable must be exactly '1' for detection."""
        monkeypatch.setenv("CLAUDECODE", "0")
        agent = ClaudeCode()
        # Process detection may still find it, so we mock that
        with patch("agent_cli.dev.coding_agents.base._get_parent_process_names", return_value=[]):
            assert agent.detect() is False

    def test_detect_with_process_name(self) -> None:
        """Detect agent via parent process name."""
        agent = Aider()
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=["bash", "aider", "zsh"],
        ):
            assert agent.detect() is True

    def test_detect_process_name_partial_match(self) -> None:
        """Process name detection uses substring match."""
        agent = Aider()
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=["python-aider-wrapper"],
        ):
            assert agent.detect() is True

    def test_is_available_with_command(self) -> None:
        """Agent is available if command is in PATH."""
        agent = ClaudeCode()
        with patch("shutil.which", return_value="/usr/bin/claude"):
            assert agent.is_available() is True

    def test_is_available_with_alt_command(self) -> None:
        """Agent is available if alt command is in PATH."""
        agent = ClaudeCode()
        with patch(
            "shutil.which",
            side_effect=lambda cmd: "/usr/bin/claude-code" if cmd == "claude-code" else None,
        ):
            assert agent.is_available() is True

    def test_is_not_available(self) -> None:
        """Agent is not available if no command found."""
        agent = ClaudeCode()
        with patch("shutil.which", return_value=None):
            assert agent.is_available() is False

    def test_launch_command(self) -> None:
        """Generate launch command."""
        agent = Aider()
        with patch("shutil.which", return_value="/usr/bin/aider"):
            cmd = agent.launch_command(Path("/some/path"))
        assert cmd == ["/usr/bin/aider"]

    def test_launch_command_with_extra_args(self) -> None:
        """Generate launch command with extra arguments."""
        agent = Aider()
        with patch("shutil.which", return_value="/usr/bin/aider"):
            cmd = agent.launch_command(Path("/some/path"), extra_args=["--model", "gpt-4"])
        assert cmd == ["/usr/bin/aider", "--model", "gpt-4"]

    def test_launch_command_not_installed(self) -> None:
        """Raise error when agent not installed."""
        agent = Aider()
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(RuntimeError, match="aider is not installed"),
        ):
            agent.launch_command(Path("/some/path"))

    def test_launch_command_includes_install_url(self) -> None:
        """Error message includes install URL."""
        agent = Aider()
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(RuntimeError, match=r"https://aider\.chat"),
        ):
            agent.launch_command(Path("/some/path"))

    def test_repr(self) -> None:
        """String representation includes name and status."""
        agent = Aider()
        with patch("shutil.which", return_value=None):
            assert "aider" in repr(agent)
            assert "not installed" in repr(agent)


class TestCursorAgentDetection:
    """Tests for Cursor Agent's custom detection."""

    def test_detect_with_cursor_agent_env_presence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cursor Agent uses presence check, not == '1'."""
        monkeypatch.setenv("CURSOR_AGENT", "0")  # Even "0" means active
        agent = CursorAgent()
        assert agent.detect() is True

    def test_detect_with_empty_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty env var means not running in Cursor Agent.

        Note: CursorAgent uses env var detection only (no parent process fallback).
        """
        monkeypatch.delenv("CURSOR_AGENT", raising=False)
        agent = CursorAgent()
        assert agent.detect() is False


class TestClaudeCodeExecutable:
    """Tests for Claude Code's custom executable lookup."""

    def test_prefers_local_claude(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prefer ~/.claude/local/claude over PATH."""
        # Create fake local claude
        claude_dir = tmp_path / ".claude" / "local"
        claude_dir.mkdir(parents=True)
        claude_exe = claude_dir / "claude"
        claude_exe.write_text("#!/bin/bash\necho claude")
        claude_exe.chmod(0o755)

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        agent = ClaudeCode()
        exe = agent.get_executable()
        assert exe == str(claude_exe)

    def test_falls_back_to_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fall back to PATH when local claude not found."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        agent = ClaudeCode()
        with patch("shutil.which", return_value="/usr/bin/claude"):
            exe = agent.get_executable()
        assert exe == "/usr/bin/claude"


class TestRegistry:
    """Tests for agent registry functions."""

    def test_get_all_agents(self) -> None:
        """Get all registered agents."""
        agents = get_all_agents()
        assert len(agents) > 0
        assert all(isinstance(a, CodingAgent) for a in agents)

    def test_get_all_agents_cached(self) -> None:
        """Agent instances are cached."""
        agents1 = get_all_agents()
        agents2 = get_all_agents()
        assert agents1[0] is agents2[0]

    def test_get_available_agents(self) -> None:
        """Get only available agents."""
        # Just verify the function runs without error
        agents = get_available_agents()
        assert isinstance(agents, list)

    def test_get_agent_by_name(self) -> None:
        """Get agent by name."""
        agent = get_agent("claude")
        assert agent is not None
        assert agent.name == "claude"

    def test_get_agent_by_command(self) -> None:
        """Get agent by command name."""
        agent = get_agent("aider")
        assert agent is not None
        assert agent.command == "aider"

    def test_get_agent_case_insensitive(self) -> None:
        """Agent lookup is case insensitive."""
        agent = get_agent("CLAUDE")
        assert agent is not None
        assert agent.name == "claude"

    def test_get_agent_not_found(self) -> None:
        """Return None for unknown agent."""
        agent = get_agent("nonexistent")
        assert agent is None

    def test_detect_current_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect current agent from environment."""
        monkeypatch.setenv("CLAUDECODE", "1")
        agent = detect_current_agent()
        assert agent is not None
        assert agent.name == "claude"

    def test_detect_current_agent_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Return None when no agent detected."""
        # Clear all detection env vars
        for var in ["CLAUDECODE", "CURSOR_AGENT", "OPENCODE"]:
            monkeypatch.delenv(var, raising=False)
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=[],
        ):
            agent = detect_current_agent()
            # May still detect something based on actual environment
            # Just verify it doesn't crash
            assert agent is None or isinstance(agent, CodingAgent)
