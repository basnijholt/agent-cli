"""Tests for dev launch helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_cli.dev.launch import launch_agent
from agent_cli.dev.terminals import TerminalHandle
from agent_cli.dev.terminals.tmux import Tmux


class TestLaunchAgent:
    """Tests for agent launch behavior."""

    def test_uses_requested_tmux_outside_tmux(self, tmp_path: Path) -> None:
        """Explicit tmux launch uses a detached repo session when not already in tmux."""
        agent = MagicMock()
        agent.name = "codex"
        agent.launch_command.return_value = ["codex"]

        tmux_terminal = Tmux()
        handle = TerminalHandle("tmux", "%42", "agent-cli-repo-1234")

        with (
            patch("agent_cli.dev.launch.terminals.get_terminal", return_value=tmux_terminal),
            patch("agent_cli.dev.launch.terminals.detect_current_terminal", return_value=None),
            patch.object(tmux_terminal, "is_available", return_value=True),
            patch.object(tmux_terminal, "detect", return_value=False),
            patch.object(
                tmux_terminal,
                "session_name_for_repo",
                return_value="agent-cli-repo-1234",
            ) as mock_session_name,
            patch.object(tmux_terminal, "open_in_session", return_value=handle) as mock_open,
            patch("agent_cli.dev.launch.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.launch.worktree.get_current_branch", return_value="feature"),
        ):
            result = launch_agent(tmp_path, agent, multiplexer_name="tmux")

        assert result == handle
        mock_session_name.assert_called_once_with(Path("/repo"))
        mock_open.assert_called_once_with(
            tmp_path,
            "codex",
            tab_name="repo@feature",
            session_name="agent-cli-repo-1234",
        )

    def test_uses_wrapper_script_for_requested_tmux(self, tmp_path: Path) -> None:
        """Prompt launches still use the wrapper script for explicit tmux sessions."""
        task_file = tmp_path / ".claude" / "TASK.md"
        task_file.parent.mkdir(parents=True)
        task_file.write_text("Fix the bug\n")
        wrapper_script = tmp_path / "agent-wrapper.sh"

        agent = MagicMock()
        agent.name = "codex"

        tmux_terminal = Tmux()
        handle = TerminalHandle("tmux", "%7", "agent-cli-repo-1234")

        with (
            patch("agent_cli.dev.launch.terminals.get_terminal", return_value=tmux_terminal),
            patch("agent_cli.dev.launch.terminals.detect_current_terminal", return_value=None),
            patch.object(tmux_terminal, "is_available", return_value=True),
            patch.object(tmux_terminal, "detect", return_value=False),
            patch.object(
                tmux_terminal,
                "session_name_for_repo",
                return_value="agent-cli-repo-1234",
            ),
            patch(
                "agent_cli.dev.launch._create_prompt_wrapper_script",
                return_value=wrapper_script,
            ),
            patch.object(tmux_terminal, "open_in_session", return_value=handle) as mock_open,
            patch("agent_cli.dev.launch.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.launch.worktree.get_current_branch", return_value="feature"),
        ):
            result = launch_agent(
                tmp_path,
                agent,
                task_file=task_file,
                multiplexer_name="tmux",
            )

        assert result == handle
        mock_open.assert_called_once_with(
            tmp_path,
            f"bash {wrapper_script}",
            tab_name="repo@feature",
            session_name="agent-cli-repo-1234",
        )
