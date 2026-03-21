"""Tests for dev launch helpers."""

from __future__ import annotations

import shlex
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_cli.dev.launch import (
    _create_prompt_wrapper_script,
    launch_agent,
    write_prompt_to_worktree,
)
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
            f"bash {shlex.quote(str(wrapper_script))}",
            tab_name="repo@feature",
            session_name="agent-cli-repo-1234",
        )

    def test_non_tmux_success_does_not_fall_back_to_manual_instructions(
        self,
        tmp_path: Path,
    ) -> None:
        """Successful non-tmux launches should not print fallback instructions."""
        agent = MagicMock()
        agent.name = "codex"
        agent.launch_command.return_value = ["codex"]

        terminal = MagicMock()
        terminal.name = "kitty"
        terminal.is_available.return_value = True
        terminal.open_new_tab.return_value = True

        with (
            patch("agent_cli.dev.launch.terminals.get_terminal", return_value=terminal),
            patch("agent_cli.dev.launch.terminals.detect_current_terminal", return_value=None),
            patch("agent_cli.dev.launch.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.launch.worktree.get_current_branch", return_value="feature"),
            patch("agent_cli.dev.launch.console.print") as mock_print,
        ):
            result = launch_agent(tmp_path, agent, multiplexer_name="kitty")

        assert result is None
        terminal.open_new_tab.assert_called_once_with(tmp_path, "codex", tab_name="repo@feature")
        printed = "\n".join(call.args[0] for call in mock_print.call_args_list if call.args)
        assert "Started codex in new kitty tab" in printed
        assert "To start codex:" not in printed

    def test_requested_tmux_unavailable_falls_back_to_manual_instructions(
        self,
        tmp_path: Path,
    ) -> None:
        """Requested tmux launch should fall back cleanly when tmux is unavailable."""
        agent = MagicMock()
        agent.name = "codex"
        agent.launch_command.return_value = ["codex"]

        tmux_terminal = Tmux()

        with (
            patch("agent_cli.dev.launch.terminals.get_terminal", return_value=tmux_terminal),
            patch("agent_cli.dev.launch.terminals.detect_current_terminal", return_value=None),
            patch.object(tmux_terminal, "is_available", return_value=False),
            patch("agent_cli.dev.launch._is_ssh_session", return_value=False),
            patch("agent_cli.dev.launch.console.print") as mock_print,
        ):
            result = launch_agent(tmp_path, agent, multiplexer_name="tmux")

        assert result is None
        printed = "\n".join(call.args[0] for call in mock_print.call_args_list if call.args)
        assert "To start codex:" in printed
        assert f"cd {tmp_path}" in printed


class TestCreatePromptWrapperScript:
    """Tests for _create_prompt_wrapper_script unique path generation."""

    def test_concurrent_launches_produce_unique_scripts(self, tmp_path: Path) -> None:
        """Two calls for the same worktree produce different script paths.

        This is a regression test for a race condition where concurrent launches
        overwrote each other's wrapper script because the path was deterministic
        (based only on worktree name).
        """
        task_file_a = tmp_path / ".claude" / "TASK-111-aaaa.md"
        task_file_b = tmp_path / ".claude" / "TASK-222-bbbb.md"
        task_file_a.parent.mkdir(parents=True)
        task_file_a.write_text("task A\n")
        task_file_b.write_text("task B\n")

        agent = MagicMock()
        agent.name = "claude"
        agent.get_executable.return_value = "/usr/bin/claude"

        path_a = _create_prompt_wrapper_script(tmp_path, agent, task_file_a)
        path_b = _create_prompt_wrapper_script(tmp_path, agent, task_file_b)

        assert path_a != path_b
        assert "TASK-111-aaaa.md" in path_a.read_text()
        assert "TASK-222-bbbb.md" in path_b.read_text()

    def test_script_is_executable(self, tmp_path: Path) -> None:
        """Generated wrapper script has execute permission."""
        task_file = tmp_path / ".claude" / "TASK-111-aaaa.md"
        task_file.parent.mkdir(parents=True)
        task_file.write_text("task\n")

        agent = MagicMock()
        agent.name = "claude"
        agent.get_executable.return_value = "/usr/bin/claude"

        path = _create_prompt_wrapper_script(tmp_path, agent, task_file)
        assert path.stat().st_mode & 0o755


class TestWritePromptToWorktree:
    """Tests for write_prompt_to_worktree unique filename generation."""

    def test_unique_task_filenames(self, tmp_path: Path) -> None:
        """Two calls produce different filenames to avoid parallel overwrites."""
        path1 = write_prompt_to_worktree(tmp_path, "task A")
        path2 = write_prompt_to_worktree(tmp_path, "task B")
        assert path1 != path2
        assert path1.read_text() == "task A\n"
        assert path2.read_text() == "task B\n"

    def test_task_file_in_claude_dir(self, tmp_path: Path) -> None:
        """File is created inside the .claude/ directory."""
        path = write_prompt_to_worktree(tmp_path, "hello")
        assert path.parent == tmp_path / ".claude"

    def test_task_filename_pattern(self, tmp_path: Path) -> None:
        """Filename matches TASK-{timestamp}-{hex}.md pattern."""
        import re  # noqa: PLC0415

        path = write_prompt_to_worktree(tmp_path, "hello")
        assert re.match(r"TASK-\d+-[0-9a-f]{4}\.md$", path.name)

    def test_task_file_contains_prompt(self, tmp_path: Path) -> None:
        """Written file contains the prompt text with trailing newline."""
        path = write_prompt_to_worktree(tmp_path, "Fix the login bug")
        assert path.read_text() == "Fix the login bug\n"

    def test_creates_claude_dir_if_missing(self, tmp_path: Path) -> None:
        """Creates .claude/ directory if it doesn't exist."""
        worktree = tmp_path / "fresh-worktree"
        worktree.mkdir()
        path = write_prompt_to_worktree(worktree, "task")
        assert path.exists()
        assert (worktree / ".claude").is_dir()
