"""Tests for dev launch preparation hooks."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.dev.hooks import LaunchContext, prepare_agent_launch


def _context(tmp_path: Path) -> LaunchContext:
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir(parents=True)
    task_file = worktree_path / ".claude" / "TASK.md"
    task_file.parent.mkdir(parents=True)

    agent = MagicMock()
    agent.name = "codex"
    agent.prepare_launch.return_value = None
    return LaunchContext(
        agent=agent,
        worktree_path=worktree_path,
        repo_root=tmp_path / "repo",
        branch="feature",
        worktree_name="feature",
        task_file=task_file,
        agent_env={"CLAUDE_CODE_USE_VERTEX": "1"},
    )


class TestPrepareAgentLaunch:
    """Tests for launch preparation."""

    def test_skips_everything_when_disabled(self, tmp_path: Path) -> None:
        """`hooks_enabled=False` should bypass trust prep and user hooks."""
        context = _context(tmp_path)
        mock_prepare = cast("Any", context.agent.prepare_launch)

        with (
            patch("agent_cli.dev._config.get_runtime_config") as mock_get_runtime_config,
            patch("agent_cli.dev.hooks.subprocess.run") as mock_run,
        ):
            prepare_agent_launch(context, hooks_enabled=False)

        mock_prepare.assert_not_called()
        mock_get_runtime_config.assert_not_called()
        mock_run.assert_not_called()

    def test_runs_auto_trust_and_global_then_agent_hooks(self, tmp_path: Path) -> None:
        """Preparation should run built-in trust then global and per-agent hooks."""
        context = _context(tmp_path)
        mock_prepare = cast("Any", context.agent.prepare_launch)
        mock_prepare.return_value = "Trusted repo"
        home = tmp_path / "home"
        home.mkdir()
        hook_path = home / "pre-launch.sh"
        hook_path.write_text("#!/bin/sh\nexit 0\n")
        expected_hook = hook_path

        with (
            patch("agent_cli.dev._config.get_runtime_config") as mock_get_runtime_config,
            patch(
                "agent_cli.dev.hooks.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ) as mock_run,
            patch("agent_cli.dev.hooks.info"),
            patch.dict(
                "os.environ",
                {"HOME": str(home), "USERPROFILE": str(home)},
                clear=False,
            ),
        ):
            mock_get_runtime_config.return_value = {
                "dev": {"auto_trust": True},
                "dev.hooks": {"pre_launch": ["~/pre-launch.sh"]},
                "dev.hooks.codex": {"pre_launch": ["codex-hook --flag"]},
            }
            expected_hook = Path("~/pre-launch.sh").expanduser()
            prepare_agent_launch(context)

        mock_prepare.assert_called_once_with(
            context.worktree_path,
            context.repo_root,
        )
        assert mock_run.call_count == 2

        first_call = mock_run.call_args_list[0]
        assert first_call.args[0] == [str(expected_hook)]
        assert first_call.kwargs["cwd"] == context.worktree_path
        assert first_call.kwargs["env"]["AGENT_CLI_AGENT"] == "codex"
        assert first_call.kwargs["env"]["AGENT_CLI_REPO_ROOT"] == str(context.repo_root)
        assert first_call.kwargs["env"]["AGENT_CLI_WORKTREE"] == str(context.worktree_path)
        assert first_call.kwargs["env"]["AGENT_CLI_TASK_FILE"] == str(context.task_file)
        assert first_call.kwargs["env"]["CLAUDE_CODE_USE_VERTEX"] == "1"

        second_call = mock_run.call_args_list[1]
        assert second_call.args[0] == ["codex-hook", "--flag"]

    def test_respects_auto_trust_false(self, tmp_path: Path) -> None:
        """Hook commands can run even when auto-trust is disabled."""
        context = _context(tmp_path)
        mock_prepare = cast("Any", context.agent.prepare_launch)

        with (
            patch(
                "agent_cli.dev._config.get_runtime_config",
                return_value={
                    "dev": {"auto_trust": False},
                    "dev.hooks": {"pre_launch": ["hook"]},
                },
            ),
            patch(
                "agent_cli.dev.hooks.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ) as mock_run,
        ):
            prepare_agent_launch(context)

        mock_prepare.assert_not_called()
        mock_run.assert_called_once()

    def test_raises_on_hook_failure(self, tmp_path: Path) -> None:
        """Non-zero hook exit should abort preparation."""
        context = _context(tmp_path)

        with (
            patch(
                "agent_cli.dev._config.get_runtime_config",
                return_value={"dev.hooks": {"pre_launch": ["broken-hook"]}},
            ),
            patch(
                "agent_cli.dev.hooks.subprocess.run",
                return_value=subprocess.CompletedProcess([], 7, "", "boom"),
            ),
            pytest.raises(RuntimeError, match="Pre-launch hook failed"),
        ):
            prepare_agent_launch(context)

    def test_rejects_invalid_hook_config(self, tmp_path: Path) -> None:
        """Hook config must be a string or list of strings."""
        context = _context(tmp_path)

        with (
            patch(
                "agent_cli.dev._config.get_runtime_config",
                return_value={"dev.hooks": {"pre_launch": {"not": "valid"}}},
            ),
            pytest.raises(RuntimeError, match=r"\[dev\.hooks\]\.pre_launch"),
        ):
            prepare_agent_launch(context)
