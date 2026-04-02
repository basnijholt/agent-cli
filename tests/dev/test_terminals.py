"""Tests for terminal adapters."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest  # noqa: TC002

from agent_cli.dev.terminals import (
    Terminal,
    detect_current_terminal,
    get_all_terminals,
    get_available_terminals,
    get_terminal,
)
from agent_cli.dev.terminals.kitty import Kitty
from agent_cli.dev.terminals.tmux import Tmux, TmuxInventory, TmuxWindow
from agent_cli.dev.terminals.zellij import Zellij


class TestTmux:
    """Tests for Tmux terminal."""

    def test_detect_tmux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect tmux via TMUX environment variable."""
        monkeypatch.setenv("TMUX", "/run/user/1000/tmux-1000/default,12345,0")
        terminal = Tmux()
        assert terminal.detect() is True

    def test_detect_tmux_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Not in tmux when TMUX not set."""
        monkeypatch.delenv("TMUX", raising=False)
        terminal = Tmux()
        assert terminal.detect() is False

    def test_is_available(self) -> None:
        """Tmux is available if command in PATH."""
        terminal = Tmux()
        with patch("shutil.which", return_value="/usr/bin/tmux"):
            assert terminal.is_available() is True

    def test_open_new_tab(self) -> None:
        """Open new tmux window."""
        terminal = Tmux()
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("subprocess.run", mock_run),
            patch.object(terminal, "current_session_name", return_value="current-session"),
            patch("shutil.which", return_value="/usr/bin/tmux"),
        ):
            result = terminal.open_new_tab(Path("/some/path"), "echo hello", tab_name="test")

        assert result is True
        # Check that tmux new-window was called
        call_args = mock_run.call_args_list[0]
        assert "new-window" in call_args[0][0]

    def test_spawn_target_tags_window_with_worktree_path(self) -> None:
        """Spawned tmux windows are tagged with the owning worktree path."""
        terminal = Tmux()
        with (
            patch("shutil.which", return_value="/usr/bin/tmux"),
            patch(
                "subprocess.run",
                side_effect=[
                    MagicMock(stdout="%42\n"),
                    MagicMock(returncode=0),
                ],
            ) as mock_run,
        ):
            handle = terminal._spawn_target(
                ["tmux", "new-window", "-t", "repo-session"],
                path=Path("/some/path"),
                command="echo hello",
                tab_name="test",
                session_name="repo-session",
            )

        assert handle is not None
        assert handle.handle == "%42"
        assert mock_run.call_args_list[1].args[0] == [
            "/usr/bin/tmux",
            "set-option",
            "-w",
            "-t",
            "%42",
            "@agent_cli_worktree",
            str(Path("/some/path").resolve()),
        ]

    def test_session_name_for_repo(self) -> None:
        """Repo session names are deterministic and shell-safe."""
        terminal = Tmux()
        session_name = terminal.session_name_for_repo(Path("/workspace/my repo"))
        assert session_name.startswith("agent-cli-my-repo-")

    def test_session_name_for_repo_replaces_tmux_target_separators(self) -> None:
        """Repo-derived tmux session names should avoid target separator characters."""
        terminal = Tmux()
        session_name = terminal.session_name_for_repo(Path("/workspace/demo.repo"))
        assert session_name.startswith("agent-cli-demo-repo-")
        assert "." not in session_name
        assert ":" not in session_name

    def test_open_in_session_creates_detached_session_when_missing(self) -> None:
        """Outside tmux, a named session is created in detached mode if absent."""
        terminal = Tmux()
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch.object(terminal, "_open_window", return_value=None) as mock_open,
            patch.object(
                terminal,
                "_create_session",
                return_value=MagicMock(handle="%42", session_name="repo-session"),
            ) as mock_create,
        ):
            handle = terminal.open_in_session(
                Path("/some/path"),
                "echo hello",
                tab_name="test",
                session_name="repo-session",
            )

        assert handle is not None
        assert handle.handle == "%42"
        assert handle.session_name == "repo-session"
        mock_open.assert_called_once_with(
            Path("/some/path"),
            "echo hello",
            "test",
            session_name="repo-session",
        )
        mock_create.assert_called_once_with(
            Path("/some/path"),
            "echo hello",
            "test",
            session_name="repo-session",
        )

    def test_create_session_disables_renumber_windows(self) -> None:
        """New tmux sessions disable window renumbering."""
        terminal = Tmux()
        mock_handle = MagicMock(handle="%42", session_name="repo-session")
        with (
            patch.object(terminal, "_spawn_target", return_value=mock_handle) as mock_spawn,
            patch("subprocess.run") as mock_run,
        ):
            handle = terminal._create_session(
                Path("/some/path"),
                "echo hello",
                "test",
                session_name="repo-session",
            )

        assert handle is mock_handle
        mock_spawn.assert_called_once_with(
            ["tmux", "new-session", "-d", "-s", "repo-session"],
            path=Path("/some/path"),
            command="echo hello",
            tab_name="test",
            session_name="repo-session",
        )
        mock_run.assert_called_once_with(
            ["tmux", "set-option", "-t", "repo-session", "renumber-windows", "off"],
            capture_output=True,
            check=False,
        )

    def test_open_in_session_reuses_existing_session(self) -> None:
        """Outside tmux, a named session gets a new window when it already exists."""
        terminal = Tmux()
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch.object(
                terminal,
                "_open_window",
                return_value=MagicMock(handle="%5", session_name="repo-session"),
            ) as mock_open,
            patch.object(terminal, "_create_session") as mock_create,
        ):
            handle = terminal.open_in_session(
                Path("/some/path"),
                "echo hello",
                tab_name="test",
                session_name="repo-session",
            )

        assert handle is not None
        assert handle.handle == "%5"
        assert handle.session_name == "repo-session"
        mock_open.assert_called_once_with(
            Path("/some/path"),
            "echo hello",
            "test",
            session_name="repo-session",
        )
        mock_create.assert_not_called()

    def test_open_in_session_retries_when_session_appears_during_race(self) -> None:
        """Concurrent creators should fall back to opening a new window."""
        terminal = Tmux()
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch.object(
                terminal,
                "_open_window",
                side_effect=[
                    None,
                    MagicMock(handle="%7", session_name="repo-session"),
                ],
            ) as mock_open,
            patch.object(terminal, "_create_session", return_value=None) as mock_create,
        ):
            handle = terminal.open_in_session(
                Path("/some/path"),
                "echo hello",
                tab_name="test",
                session_name="repo-session",
            )

        assert handle is not None
        assert handle.handle == "%7"
        assert handle.session_name == "repo-session"
        assert mock_open.call_count == 2
        mock_create.assert_called_once_with(
            Path("/some/path"),
            "echo hello",
            "test",
            session_name="repo-session",
        )

    def test_list_windows_for_worktree_searches_all_sessions(self) -> None:
        """Cross-session inventory should filter tagged windows by worktree path."""
        terminal = Tmux()
        stdout = (
            "@1\tsession-a\teditor\t/other/path\n"
            "@2\tsession-a\tagent-one\t/some/path\n"
            "@3\tsession-b\tagent-two\t/some/path"
        )
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch("subprocess.run", return_value=MagicMock(stdout=stdout)) as mock_run,
        ):
            inventory = terminal.list_windows_for_worktree(Path("/some/path"))

        assert inventory.error is None
        assert inventory.windows == (
            TmuxWindow(window_id="@2", session_name="session-a", window_name="agent-one"),
            TmuxWindow(window_id="@3", session_name="session-b", window_name="agent-two"),
        )
        assert mock_run.call_args.args[0] == [
            "tmux",
            "list-windows",
            "-a",
            "-F",
            "#{window_id}\t#{session_name}\t#{window_name}\t#{@agent_cli_worktree}",
        ]

    def test_list_windows_for_worktree_returns_empty_when_no_server_running(self) -> None:
        """No running tmux server should be treated as an empty inventory."""
        terminal = Tmux()
        error = subprocess.CalledProcessError(
            1,
            ["tmux", "list-windows", "-a", "-F", "#{window_id}"],
            stderr="no server running on /tmp/tmux-1000/default\n",
        )
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch("subprocess.run", side_effect=error),
        ):
            inventory = terminal.list_windows_for_worktree(Path("/some/path"))

        assert inventory == TmuxInventory()

    def test_kill_windows_for_worktree_uses_inventory_window_ids(self) -> None:
        """Tagged windows are killed by window id across sessions."""
        terminal = Tmux()
        inventory = TmuxInventory(
            windows=(
                TmuxWindow(window_id="@2", session_name="session-a", window_name="agent-one"),
                TmuxWindow(window_id="@3", session_name="session-b", window_name="agent-two"),
            ),
        )
        with (
            patch.object(terminal, "list_windows_for_worktree", return_value=inventory),
            patch.object(terminal, "current_window_id", return_value=None),
            patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run,
        ):
            cleanup = terminal.kill_windows_for_worktree(Path("/some/path"))

        assert cleanup.errors == ()
        assert cleanup.killed_windows == inventory.windows
        assert [call.args[0] for call in mock_run.call_args_list] == [
            ["tmux", "kill-window", "-t", "@2"],
            ["tmux", "kill-window", "-t", "@3"],
        ]

    def test_kill_windows_for_worktree_skips_current_window(self) -> None:
        """Cleanup should not kill the tmux window running the command."""
        terminal = Tmux()
        inventory = TmuxInventory(
            windows=(
                TmuxWindow(window_id="@2", session_name="session-a", window_name="agent-one"),
                TmuxWindow(window_id="@3", session_name="session-b", window_name="agent-two"),
            ),
        )
        with (
            patch.object(terminal, "list_windows_for_worktree", return_value=inventory),
            patch.object(terminal, "current_window_id", return_value="@2"),
            patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run,
        ):
            cleanup = terminal.kill_windows_for_worktree(Path("/some/path"))

        assert cleanup.errors == (
            "Skipped tmux window @2 in session session-a because it is the current window",
        )
        assert cleanup.killed_windows == (inventory.windows[1],)
        assert [call.args[0] for call in mock_run.call_args_list] == [
            ["tmux", "kill-window", "-t", "@3"],
        ]


class TestZellij:
    """Tests for Zellij terminal."""

    def test_detect_zellij(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect zellij via ZELLIJ environment variable."""
        monkeypatch.setenv("ZELLIJ", "0")  # Zellij uses presence, not value
        terminal = Zellij()
        assert terminal.detect() is True

    def test_detect_zellij_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Not in zellij when ZELLIJ not set."""
        monkeypatch.delenv("ZELLIJ", raising=False)
        terminal = Zellij()
        assert terminal.detect() is False

    def test_is_available(self) -> None:
        """Zellij is available if command in PATH."""
        terminal = Zellij()
        with patch("shutil.which", return_value="/usr/bin/zellij"):
            assert terminal.is_available() is True


class TestKitty:
    """Tests for Kitty terminal."""

    def test_detect_kitty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect kitty via KITTY_WINDOW_ID environment variable."""
        monkeypatch.setenv("KITTY_WINDOW_ID", "1")
        terminal = Kitty()
        assert terminal.detect() is True

    def test_detect_kitty_term(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect kitty via TERM."""
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.setenv("TERM", "xterm-kitty")
        terminal = Kitty()
        assert terminal.detect() is True

    def test_is_available(self) -> None:
        """Kitty is available if command in PATH."""
        terminal = Kitty()
        with patch("shutil.which", return_value="/usr/bin/kitty"):
            assert terminal.is_available() is True


class TestRegistry:
    """Tests for terminal registry functions."""

    def test_get_all_terminals(self) -> None:
        """Get all registered terminals."""
        terminals = get_all_terminals()
        assert len(terminals) > 0
        assert all(isinstance(t, Terminal) for t in terminals)

    def test_get_all_terminals_cached(self) -> None:
        """Terminal instances are cached."""
        terminals1 = get_all_terminals()
        terminals2 = get_all_terminals()
        assert terminals1[0] is terminals2[0]

    def test_get_terminal_by_name(self) -> None:
        """Get terminal by name."""
        terminal = get_terminal("tmux")
        assert terminal is not None
        assert terminal.name == "tmux"

    def test_get_terminal_not_found(self) -> None:
        """Return None for unknown terminal."""
        terminal = get_terminal("nonexistent")
        assert terminal is None

    def test_detect_current_terminal_tmux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect current terminal as tmux."""
        monkeypatch.setenv("TMUX", "/run/user/1000/tmux")
        terminal = detect_current_terminal()
        assert terminal is not None
        assert terminal.name == "tmux"

    def test_detect_current_terminal_zellij(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect current terminal as zellij."""
        monkeypatch.delenv("TMUX", raising=False)
        monkeypatch.setenv("ZELLIJ", "0")
        terminal = detect_current_terminal()
        assert terminal is not None
        assert terminal.name == "zellij"

    def test_get_available_terminals(self) -> None:
        """Get available terminals returns list."""
        terminals = get_available_terminals()
        assert isinstance(terminals, list)
