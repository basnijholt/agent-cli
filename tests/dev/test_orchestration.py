"""Tests for agent orchestration (tmux_ops, agent_state, poll/output/send/wait)."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from agent_cli.cli import app
from agent_cli.dev import agent_state, launch, poller, tmux_ops
from agent_cli.dev.agent_state import inject_completion_hook
from agent_cli.dev.terminals.tmux import Tmux

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})

_TMUX_ENV = {"TMUX": "/tmp/tmux-1000/default,12345,0"}  # noqa: S108


# ---------------------------------------------------------------------------
# tmux_ops tests
# ---------------------------------------------------------------------------


class TestTmuxOps:
    """Tests for low-level tmux operations."""

    def test_open_window_with_pane_id(self) -> None:
        """Returns pane ID from tmux new-window -P."""
        mock_result = MagicMock(stdout="%42\n")
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            pane_id = tmux_ops.open_window_with_pane_id(Path("/tmp/test"))  # noqa: S108
            assert pane_id == "%42"
            cmd = mock_run.call_args[0][0]
            assert "new-window" in cmd
            assert "-P" in cmd
            assert "#{pane_id}" in cmd

    def test_open_window_with_tab_name_and_command(self) -> None:
        """Passes tab name and command to tmux."""
        mock_result = MagicMock(stdout="%5\n")
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            pane_id = tmux_ops.open_window_with_pane_id(
                Path("/tmp/test"),  # noqa: S108
                command="echo hello",
                tab_name="test-tab",
            )
            assert pane_id == "%5"
            cmd = mock_run.call_args[0][0]
            assert "-n" in cmd
            assert "test-tab" in cmd
            assert "echo hello" in cmd

    def test_open_window_returns_none_on_failure(self) -> None:
        """Returns None when tmux command fails."""
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "tmux")):
            assert tmux_ops.open_window_with_pane_id(Path("/tmp")) is None  # noqa: S108

    def test_capture_pane(self) -> None:
        """Captures pane output from tmux."""
        mock_result = MagicMock(stdout="line1\nline2\n")
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            output = tmux_ops.capture_pane("%3", lines=100)
            assert output == "line1\nline2\n"
            cmd = mock_run.call_args[0][0]
            assert "-t" in cmd
            assert "%3" in cmd
            assert "-100" in cmd

    def test_capture_pane_returns_none_on_failure(self) -> None:
        """Returns None when pane doesn't exist."""
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "tmux")):
            assert tmux_ops.capture_pane("%99") is None

    def test_send_keys(self) -> None:
        """Sends keys to tmux pane."""
        with patch("subprocess.run") as mock_run:
            assert tmux_ops.send_keys("%3", "hello") is True
            cmd = mock_run.call_args[0][0]
            assert "send-keys" in cmd
            assert "%3" in cmd
            assert "hello" in cmd
            assert "Enter" in cmd

    def test_send_keys_no_enter(self) -> None:
        """Sends keys without pressing Enter."""
        with patch("subprocess.run") as mock_run:
            tmux_ops.send_keys("%3", "hello", enter=False)
            cmd = mock_run.call_args[0][0]
            assert "Enter" not in cmd

    def test_send_keys_returns_false_on_failure(self) -> None:
        """Returns False when tmux command fails."""
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "tmux")):
            assert tmux_ops.send_keys("%3", "hello") is False

    def test_pane_exists(self) -> None:
        """Checks pane existence via list-panes."""
        mock_result = MagicMock(stdout="%1\n%3\n%5\n")
        with patch("subprocess.run", return_value=mock_result):
            assert tmux_ops.pane_exists("%3") is True
            assert tmux_ops.pane_exists("%99") is False

    def test_pane_exists_returns_false_on_failure(self) -> None:
        """Returns False when tmux is not available."""
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "tmux")):
            assert tmux_ops.pane_exists("%3") is False

    def test_hash_output(self) -> None:
        """Produces consistent SHA-256 hashes."""
        h1 = tmux_ops.hash_output("hello")
        h2 = tmux_ops.hash_output("hello")
        h3 = tmux_ops.hash_output("world")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 64  # SHA-256 hex digest


# ---------------------------------------------------------------------------
# agent_state tests
# ---------------------------------------------------------------------------


class TestAgentState:
    """Tests for agent state management."""

    def test_repo_slug(self) -> None:
        """Generates filesystem-safe slug from path."""
        slug = agent_state._repo_slug(Path("/home/user/Work/my-project"))
        assert "my-project" in slug
        assert "/" not in slug

    def test_repo_slug_avoids_cross_clone_collisions(self) -> None:
        """Distinct roots with same tail produce different slugs."""
        slug1 = agent_state._repo_slug(Path("/Users/alice/Work/my-project"))
        slug2 = agent_state._repo_slug(Path("/Volumes/external/Work/my-project"))
        assert slug1 != slug2

    def test_load_empty_state(self, tmp_path: Path) -> None:
        """Returns empty state when no file exists."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            state = agent_state.load_state(tmp_path / "repo")
            assert state.agents == {}
            assert state.last_poll_at == 0.0

    def test_load_state_ignores_unknown_agent_fields(self, tmp_path: Path) -> None:
        """Loads agent rows even when old schema includes extra fields."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            repo = tmp_path / "repo"
            state_path = agent_state._state_file_path(repo)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps(
                    {
                        "agents": {
                            "agent": {
                                "name": "agent",
                                "pane_id": "%42",
                                "worktree_path": str(tmp_path / "wt"),
                                "agent_type": "claude",
                                "started_at": 123.0,
                                "status": "running",
                                # Older schema fields should be ignored.
                                "last_output_hash": "",
                                "last_change_at": 123.0,
                            },
                        },
                        "last_poll_at": 12.5,
                    },
                ),
            )

            state = agent_state.load_state(repo)
            assert "agent" in state.agents
            assert state.last_poll_at == 12.5

    def test_save_and_load_state(self, tmp_path: Path) -> None:
        """Round-trips state through JSON."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            repo = tmp_path / "repo"
            agent = agent_state.register_agent(
                repo,
                "test-agent",
                "%42",
                tmp_path / "worktree",
                "claude",
            )
            assert agent.name == "test-agent"
            assert agent.pane_id == "%42"

            state = agent_state.load_state(repo)
            assert "test-agent" in state.agents
            assert state.agents["test-agent"].pane_id == "%42"
            assert state.agents["test-agent"].agent_type == "claude"

    def test_generate_agent_name_first(self, tmp_path: Path) -> None:
        """First agent in worktree uses branch name."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            repo = tmp_path / "repo"
            name = agent_state.generate_agent_name(repo, tmp_path / "auth", "claude")
            assert name == "auth"

    def test_generate_agent_name_second(self, tmp_path: Path) -> None:
        """Second agent appends agent type."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            repo = tmp_path / "repo"
            agent_state.register_agent(repo, "auth", "%1", tmp_path / "auth", "claude")
            name = agent_state.generate_agent_name(repo, tmp_path / "auth", "claude")
            assert name == "auth-claude"

    def test_generate_agent_name_collision(self, tmp_path: Path) -> None:
        """Numeric suffix on further collisions."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            repo = tmp_path / "repo"
            agent_state.register_agent(repo, "auth", "%1", tmp_path / "auth", "claude")
            agent_state.register_agent(repo, "auth-claude", "%2", tmp_path / "auth", "claude")
            name = agent_state.generate_agent_name(repo, tmp_path / "auth", "claude")
            assert name == "auth-claude-2"

    def test_generate_agent_name_explicit(self, tmp_path: Path) -> None:
        """Explicit name is used directly."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            repo = tmp_path / "repo"
            name = agent_state.generate_agent_name(
                repo,
                tmp_path / "auth",
                "claude",
                explicit_name="reviewer",
            )
            assert name == "reviewer"

    def test_generate_agent_name_explicit_collision(self, tmp_path: Path) -> None:
        """Explicit name raises ValueError on collision."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            repo = tmp_path / "repo"
            agent_state.register_agent(repo, "reviewer", "%1", tmp_path / "auth", "claude")
            with pytest.raises(ValueError, match="already exists"):
                agent_state.generate_agent_name(
                    repo,
                    tmp_path / "auth",
                    "claude",
                    explicit_name="reviewer",
                )

    def test_generate_agent_name_allows_reuse_after_done(self, tmp_path: Path) -> None:
        """Explicit names can be reused when prior run is terminal."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            repo = tmp_path / "repo"
            agent_state.register_agent(repo, "reviewer", "%1", tmp_path / "auth", "claude")

            state = agent_state.load_state(repo)
            state.agents["reviewer"].status = "done"
            agent_state.save_state(repo, state)

            name = agent_state.generate_agent_name(
                repo,
                tmp_path / "auth",
                "claude",
                explicit_name="reviewer",
            )
            assert name == "reviewer"

    def test_load_corrupt_state(self, tmp_path: Path) -> None:
        """Returns empty state on corrupt JSON."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            path = agent_state._state_file_path(tmp_path / "repo")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not valid json{{{")
            state = agent_state.load_state(tmp_path / "repo")
            assert state.agents == {}


# ---------------------------------------------------------------------------
# launch/poller regression tests
# ---------------------------------------------------------------------------


class TestLaunchTracking:
    """Tests for tracked launch edge cases."""

    def test_tracked_launch_validates_name_before_opening_tmux_window(self, tmp_path: Path) -> None:
        """Duplicate tracked name should fail without creating a tmux window."""
        agent = MagicMock()
        agent.name = "claude"
        agent.launch_command.return_value = ["claude"]

        with (
            patch("agent_cli.dev.launch.terminals.detect_current_terminal", return_value=Tmux()),
            patch("agent_cli.dev.launch.worktree.get_main_repo_root", return_value=tmp_path),
            patch("agent_cli.dev.launch.worktree.get_current_branch", return_value="feature"),
            patch(
                "agent_cli.dev.agent_state.generate_agent_name",
                side_effect=ValueError("name exists"),
            ),
            patch("agent_cli.dev.tmux_ops.open_window_with_pane_id") as mock_open_window,
        ):
            with pytest.raises(typer.Exit) as exc:
                launch.launch_agent(tmp_path, agent, track=True, agent_name="reviewer")
            assert exc.value.exit_code == 1
            mock_open_window.assert_not_called()

    def test_tracked_claude_launch_clears_stale_done_file(self, tmp_path: Path) -> None:
        """Tracked Claude launch removes stale completion sentinel before spawn."""
        done_path = tmp_path / ".claude" / "DONE"
        done_path.parent.mkdir(parents=True, exist_ok=True)
        done_path.write_text("stale\n")

        agent = MagicMock()
        agent.name = "claude"
        agent.launch_command.return_value = ["claude"]

        with (
            patch("agent_cli.dev.launch.terminals.detect_current_terminal", return_value=Tmux()),
            patch("agent_cli.dev.launch.worktree.get_main_repo_root", return_value=tmp_path),
            patch("agent_cli.dev.launch.worktree.get_current_branch", return_value="feature"),
            patch("agent_cli.dev.agent_state.generate_agent_name", return_value="reviewer"),
            patch("agent_cli.dev.tmux_ops.open_window_with_pane_id", return_value="%7"),
            patch("agent_cli.dev.agent_state.register_agent"),
            patch("agent_cli.dev.agent_state.inject_completion_hook"),
        ):
            result = launch.launch_agent(tmp_path, agent, track=True)
            assert result == "reviewer"
            assert not done_path.exists()


class TestPollerRegression:
    """Regression tests for completion detection logic."""

    def test_poll_ignores_done_sentinel_for_non_claude_agents(self, tmp_path: Path) -> None:
        """Non-Claude agents should not be marked done by stale Claude sentinels."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            repo = tmp_path / "repo"
            wt = tmp_path / "worktree"
            done_path = wt / ".claude" / "DONE"
            done_path.parent.mkdir(parents=True, exist_ok=True)
            done_path.write_text("stale\n")

            agent_state.register_agent(repo, "worker", "%3", wt, "codex")

            with (
                patch("agent_cli.dev.tmux_ops.pane_exists", return_value=True),
                patch("agent_cli.dev.tmux_ops.capture_pane", return_value="output"),
                patch("agent_cli.dev.tmux_ops.hash_output", return_value="h1"),
            ):
                statuses = poller.poll_once(repo)
                assert statuses["worker"] == "running"

    def test_wait_ignores_done_sentinel_for_non_claude_agents(self, tmp_path: Path) -> None:
        """wait_for_agent should use quiescence for non-Claude agents even if DONE exists."""
        with patch.object(agent_state, "STATE_BASE", tmp_path / ".cache"):
            repo = tmp_path / "repo"
            wt = tmp_path / "worktree"
            done_path = wt / ".claude" / "DONE"
            done_path.parent.mkdir(parents=True, exist_ok=True)
            done_path.write_text("stale\n")

            agent_state.register_agent(repo, "worker", "%3", wt, "codex")

            with (
                patch("agent_cli.dev.tmux_ops.pane_exists", return_value=True),
                patch("agent_cli.dev.tmux_ops.capture_pane", return_value="output"),
                patch("agent_cli.dev.tmux_ops.hash_output", return_value="h1"),
            ):
                status, _elapsed = poller.wait_for_agent(repo, "worker", timeout=1, interval=0)
                assert status == "quiet"


# ---------------------------------------------------------------------------
# CLI command tests
# ---------------------------------------------------------------------------


class TestPollCommand:
    """Tests for dev poll command."""

    def test_poll_no_agents(self) -> None:
        """Shows message when no agents are tracked."""
        with (
            patch.dict("os.environ", _TMUX_ENV),
            patch("agent_cli.dev.orchestration._ensure_git_repo", return_value=Path("/repo")),
            patch(
                "agent_cli.dev.agent_state.load_state",
                return_value=agent_state.AgentStateFile(),
            ),
        ):
            result = runner.invoke(app, ["dev", "poll"])
            assert result.exit_code == 0
            assert "No tracked agents" in result.output

    def test_poll_json_output(self) -> None:
        """Returns JSON with agent status."""
        state = agent_state.AgentStateFile()
        state.agents["test"] = agent_state.TrackedAgent(
            name="test",
            pane_id="%3",
            worktree_path="/tmp/wt",  # noqa: S108
            agent_type="claude",
            started_at=time.time() - 60,
        )

        with (
            patch.dict("os.environ", _TMUX_ENV),
            patch("agent_cli.dev.orchestration._ensure_git_repo", return_value=Path("/repo")),
            patch("agent_cli.dev.agent_state.load_state", return_value=state),
            patch("agent_cli.dev.agent_state.save_state"),
            patch("agent_cli.dev.tmux_ops.pane_exists", return_value=True),
            patch("agent_cli.dev.tmux_ops.capture_pane", return_value="output"),
            patch("agent_cli.dev.tmux_ops.hash_output", return_value="abc123"),
        ):
            result = runner.invoke(app, ["dev", "poll", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data["agents"]) == 1
            assert data["agents"][0]["name"] == "test"

    def test_poll_detects_dead_agent(self) -> None:
        """Marks agent as dead when pane is gone."""
        state = agent_state.AgentStateFile()
        state.agents["test"] = agent_state.TrackedAgent(
            name="test",
            pane_id="%3",
            worktree_path="/tmp/wt",  # noqa: S108
            agent_type="claude",
            started_at=time.time(),
        )

        with (
            patch.dict("os.environ", _TMUX_ENV),
            patch("agent_cli.dev.orchestration._ensure_git_repo", return_value=Path("/repo")),
            patch("agent_cli.dev.agent_state.load_state", return_value=state),
            patch("agent_cli.dev.agent_state.save_state"),
            patch("agent_cli.dev.tmux_ops.pane_exists", return_value=False),
        ):
            result = runner.invoke(app, ["dev", "poll", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["agents"][0]["status"] == "dead"


class TestOutputCommand:
    """Tests for dev output command."""

    def test_output_captures_pane(self) -> None:
        """Captures and prints pane output."""
        state = agent_state.AgentStateFile()
        state.agents["test"] = agent_state.TrackedAgent(
            name="test",
            pane_id="%3",
            worktree_path="/tmp/wt",  # noqa: S108
            agent_type="claude",
            started_at=time.time(),
            status="running",
        )

        with (
            patch.dict("os.environ", _TMUX_ENV),
            patch("agent_cli.dev.orchestration._ensure_git_repo", return_value=Path("/repo")),
            patch("agent_cli.dev.agent_state.load_state", return_value=state),
            patch("agent_cli.dev.tmux_ops.capture_pane", return_value="hello world\n"),
        ):
            result = runner.invoke(app, ["dev", "output", "test"])
            assert result.exit_code == 0
            assert "hello world" in result.output

    def test_output_agent_not_found(self) -> None:
        """Errors when agent name doesn't exist."""
        with (
            patch.dict("os.environ", _TMUX_ENV),
            patch("agent_cli.dev.orchestration._ensure_git_repo", return_value=Path("/repo")),
            patch(
                "agent_cli.dev.agent_state.load_state",
                return_value=agent_state.AgentStateFile(),
            ),
        ):
            result = runner.invoke(app, ["dev", "output", "nonexistent"])
            assert result.exit_code == 1
            assert "not found" in result.output


class TestSendCommand:
    """Tests for dev send command."""

    def test_send_keys_to_agent(self) -> None:
        """Sends keys to agent's tmux pane."""
        state = agent_state.AgentStateFile()
        state.agents["test"] = agent_state.TrackedAgent(
            name="test",
            pane_id="%3",
            worktree_path="/tmp/wt",  # noqa: S108
            agent_type="claude",
            started_at=time.time(),
            status="running",
        )

        with (
            patch.dict("os.environ", _TMUX_ENV),
            patch("agent_cli.dev.orchestration._ensure_git_repo", return_value=Path("/repo")),
            patch("agent_cli.dev.agent_state.load_state", return_value=state),
            patch("agent_cli.dev.tmux_ops.send_keys", return_value=True) as mock_send,
        ):
            result = runner.invoke(app, ["dev", "send", "test", "fix the tests"])
            assert result.exit_code == 0
            mock_send.assert_called_once_with("%3", "fix the tests", enter=True)

    def test_send_to_dead_agent(self) -> None:
        """Errors when sending to dead agent."""
        state = agent_state.AgentStateFile()
        state.agents["test"] = agent_state.TrackedAgent(
            name="test",
            pane_id="%3",
            worktree_path="/tmp/wt",  # noqa: S108
            agent_type="claude",
            started_at=time.time(),
            status="dead",
        )

        with (
            patch.dict("os.environ", _TMUX_ENV),
            patch("agent_cli.dev.orchestration._ensure_git_repo", return_value=Path("/repo")),
            patch("agent_cli.dev.agent_state.load_state", return_value=state),
        ):
            result = runner.invoke(app, ["dev", "send", "test", "hello"])
            assert result.exit_code == 1
            assert "dead" in result.output


class TestWaitCommand:
    """Tests for dev wait command."""

    def test_wait_already_done(self) -> None:
        """Returns immediately if agent is already done."""
        state = agent_state.AgentStateFile()
        state.agents["test"] = agent_state.TrackedAgent(
            name="test",
            pane_id="%3",
            worktree_path="/tmp/wt",  # noqa: S108
            agent_type="claude",
            started_at=time.time(),
            status="done",
        )

        with (
            patch.dict("os.environ", _TMUX_ENV),
            patch("agent_cli.dev.orchestration._ensure_git_repo", return_value=Path("/repo")),
            patch("agent_cli.dev.agent_state.load_state", return_value=state),
        ):
            result = runner.invoke(app, ["dev", "wait", "test"])
            assert result.exit_code == 0
            assert "already" in result.output

    def test_wait_already_dead(self) -> None:
        """Returns exit code 1 if agent is dead."""
        state = agent_state.AgentStateFile()
        state.agents["test"] = agent_state.TrackedAgent(
            name="test",
            pane_id="%3",
            worktree_path="/tmp/wt",  # noqa: S108
            agent_type="claude",
            started_at=time.time(),
            status="dead",
        )

        with (
            patch.dict("os.environ", _TMUX_ENV),
            patch("agent_cli.dev.orchestration._ensure_git_repo", return_value=Path("/repo")),
            patch("agent_cli.dev.agent_state.load_state", return_value=state),
        ):
            result = runner.invoke(app, ["dev", "wait", "test"])
            assert result.exit_code == 1


class TestNotInTmux:
    """Tests for tmux requirement enforcement."""

    def test_poll_requires_tmux(self) -> None:
        """Poll command fails outside tmux."""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("agent_cli.dev.orchestration._ensure_git_repo", return_value=Path("/repo")),
        ):
            result = runner.invoke(app, ["dev", "poll"])
            assert result.exit_code == 1
            assert "tmux" in result.output.lower()

    def test_send_requires_tmux(self) -> None:
        """Send command fails outside tmux."""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("agent_cli.dev.orchestration._ensure_git_repo", return_value=Path("/repo")),
        ):
            result = runner.invoke(app, ["dev", "send", "test", "hello"])
            assert result.exit_code == 1


class TestInjectCompletionHook:
    """Tests for Claude Code hook injection."""

    def test_injects_stop_hook(self, tmp_path: Path) -> None:
        """Creates .claude/settings.local.json with Stop hook."""
        inject_completion_hook(tmp_path, "claude")

        settings_path = tmp_path / ".claude" / "settings.local.json"
        assert settings_path.exists()
        settings = json.loads(settings_path.read_text())
        assert "hooks" in settings
        assert "Stop" in settings["hooks"]
        hooks = settings["hooks"]["Stop"]
        assert any(
            any(
                isinstance(hook, dict) and hook.get("command") == "touch .claude/DONE"
                for hook in h.get("hooks", [])
            )
            for h in hooks
        )

    def test_merges_with_existing_settings(self, tmp_path: Path) -> None:
        """Preserves existing settings when injecting hook."""
        settings_path = tmp_path / ".claude" / "settings.local.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({"model": "opus", "hooks": {"PreToolUse": []}}))

        inject_completion_hook(tmp_path, "claude")

        settings = json.loads(settings_path.read_text())
        assert settings["model"] == "opus"
        assert "PreToolUse" in settings["hooks"]
        assert "Stop" in settings["hooks"]

    def test_skips_non_claude_agents(self, tmp_path: Path) -> None:
        """Does nothing for non-Claude agents."""
        inject_completion_hook(tmp_path, "aider")
        assert not (tmp_path / ".claude" / "settings.local.json").exists()

    def test_idempotent(self, tmp_path: Path) -> None:
        """Doesn't duplicate hook on repeated calls."""
        inject_completion_hook(tmp_path, "claude")
        inject_completion_hook(tmp_path, "claude")

        settings = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
        stop_hooks = settings["hooks"]["Stop"]
        sentinel_count = sum(
            1
            for h in stop_hooks
            if any(
                isinstance(hook, dict) and hook.get("command") == "touch .claude/DONE"
                for hook in h.get("hooks", [])
            )
        )
        assert sentinel_count == 1
