"""Tests for terminal adapters."""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest  # noqa: TC002

from agent_cli.dev.terminals import (
    Terminal,
    TerminalHandle,
    detect_current_terminal,
    get_all_terminals,
    get_available_terminals,
    get_terminal,
)
from agent_cli.dev.terminals.cmux import Cmux
from agent_cli.dev.terminals.kitty import Kitty
from agent_cli.dev.terminals.tmux import Tmux, TmuxInventory, TmuxWindow
from agent_cli.dev.terminals.zellij import Zellij, ZellijInventory, ZellijTab


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
        some_path = terminal._normalize_worktree_path(Path("/some/path"))
        other_path = terminal._normalize_worktree_path(Path("/other/path"))
        stdout = (
            f"@1\tsession-a\teditor\t{other_path}\n"
            f"@2\tsession-a\tagent-one\t{some_path}\n"
            f"@3\tsession-b\tagent-two\t{some_path}"
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

    def test_kill_windows_for_worktree_uses_inventory_window_ids_outside_tmux(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Outside tmux, cleanup should not treat the server's active window as current."""
        terminal = Tmux()
        inventory = TmuxInventory(
            windows=(
                TmuxWindow(window_id="@2", session_name="session-a", window_name="agent-one"),
                TmuxWindow(window_id="@3", session_name="session-b", window_name="agent-two"),
            ),
        )
        monkeypatch.delenv("TMUX", raising=False)
        monkeypatch.delenv("TMUX_PANE", raising=False)
        with (
            patch.object(terminal, "list_windows_for_worktree", return_value=inventory),
            patch.object(terminal, "current_window_id", return_value="@2") as mock_current_window,
            patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run,
        ):
            cleanup = terminal.kill_windows_for_worktree(Path("/some/path"))

        mock_current_window.assert_not_called()
        assert cleanup.errors == ()
        assert cleanup.killed_windows == inventory.windows
        assert [call.args[0] for call in mock_run.call_args_list] == [
            ["tmux", "kill-window", "-t", "@2"],
            ["tmux", "kill-window", "-t", "@3"],
        ]

    def test_kill_windows_for_worktree_skips_current_window(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cleanup should not kill the tmux window running the command."""
        terminal = Tmux()
        inventory = TmuxInventory(
            windows=(
                TmuxWindow(window_id="@2", session_name="session-a", window_name="agent-one"),
                TmuxWindow(window_id="@3", session_name="session-b", window_name="agent-two"),
            ),
        )
        monkeypatch.setenv("TMUX", "/run/user/1000/tmux-1000/default,12345,0")
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

    def test_current_session_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Current session name comes from ZELLIJ_SESSION_NAME."""
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "my-session")
        assert Zellij().current_session_name() == "my-session"

    def test_attach_command_quotes_session_name(self) -> None:
        """Attach hints quote session names for the shell."""
        assert Zellij().attach_command("my session") == "zellij attach 'my session'"

    def test_cli_version_parsing(self) -> None:
        """Version is parsed from `zellij --version` output."""
        with patch("subprocess.run", return_value=MagicMock(stdout="zellij 0.44.3\n")):
            assert Zellij._cli_version() == (0, 44, 3)

    def test_open_in_session_creates_detached_session_when_missing(self) -> None:
        """Outside zellij, a named session is created in detached mode if absent."""
        terminal = Zellij()
        path = Path("/some/path")
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch.object(terminal, "_supports_cli_control", return_value=True),
            patch(
                "subprocess.run",
                side_effect=[
                    MagicMock(returncode=0),  # attach --create-background
                    MagicMock(returncode=0, stdout="3\n"),  # action new-tab
                ],
            ) as mock_run,
        ):
            handle = terminal.open_in_session(
                path,
                "echo hello",
                tab_name="feature",
                session_name="repo-session",
            )

        assert handle is not None
        assert handle.handle == "3"
        assert handle.session_name == "repo-session"
        assert mock_run.call_args_list[0].args[0] == [
            "zellij",
            "attach",
            "--create-background",
            "repo-session",
        ]
        assert mock_run.call_args_list[1].args[0] == [
            "zellij",
            "--session",
            "repo-session",
            "action",
            "new-tab",
            "--cwd",
            str(path),
            "--name",
            "feature",
            "--",
            "/bin/sh",
            "-c",
            "echo hello",
        ]

    def test_open_in_session_reuses_existing_session(self) -> None:
        """An existing session is reused when create-background reports it exists."""
        terminal = Zellij()
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch.object(terminal, "_supports_cli_control", return_value=True),
            patch(
                "subprocess.run",
                side_effect=[
                    MagicMock(returncode=1, stdout="Session already exists\n", stderr=""),
                    MagicMock(returncode=0, stdout="4\n"),
                ],
            ),
        ):
            handle = terminal.open_in_session(
                Path("/some/path"),
                "echo hello",
                session_name="repo-session",
            )

        assert handle is not None
        assert handle.handle == "4"

    def test_open_in_session_uses_current_session_inside_zellij(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Inside zellij without a named session, the current session is used."""
        monkeypatch.setenv("ZELLIJ", "0")
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "current-session")
        terminal = Zellij()
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch.object(terminal, "_supports_cli_control", return_value=True),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="2\n")) as mock_run,
        ):
            handle = terminal.open_in_session(Path("/some/path"), "echo hello")

        assert handle is not None
        assert handle.session_name == "current-session"
        assert mock_run.call_args.args[0][:3] == ["zellij", "action", "new-tab"]

    def test_open_in_session_requires_modern_zellij(self) -> None:
        """Multiplexer control is gated on zellij >= 0.44.0."""
        terminal = Zellij()
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch.object(Zellij, "_cli_version", return_value=(0, 43, 1)),
            patch("subprocess.run") as mock_run,
        ):
            handle = terminal.open_in_session(
                Path("/some/path"),
                "echo hello",
                session_name="repo-session",
            )

        assert handle is None
        mock_run.assert_not_called()

    def test_open_new_tab_falls_back_to_legacy_on_old_zellij(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Zellij < 0.44 opens tabs via the legacy write-chars path."""
        monkeypatch.setenv("ZELLIJ", "0")
        terminal = Zellij()
        path = Path("/some/path")
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch.object(Zellij, "_cli_version", return_value=(0, 41, 2)),
            patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run,
            patch("time.sleep"),
        ):
            result = terminal.open_new_tab(path, "echo hello", tab_name="feature")

        assert result is True
        commands = [call.args[0] for call in mock_run.call_args_list]
        assert commands == [
            [
                "zellij",
                "action",
                "new-tab",
                "--layout",
                "default",
                "--cwd",
                str(path),
                "--name",
                "feature",
            ],
            ["zellij", "action", "write-chars", "echo hello"],
            ["zellij", "action", "write", "10"],
        ]

    def test_open_new_tab_uses_open_in_session_on_modern_zellij(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Zellij >= 0.44 opens tabs with an initial command instead of write-chars."""
        monkeypatch.setenv("ZELLIJ", "0")
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "current-session")
        terminal = Zellij()
        path = Path("/some/path")
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch.object(Zellij, "_cli_version", return_value=(0, 44, 0)),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="2\n")) as mock_run,
        ):
            result = terminal.open_new_tab(path, "echo hello", tab_name="feature")

        assert result is True
        assert mock_run.call_args.args[0] == [
            "zellij",
            "action",
            "new-tab",
            "--cwd",
            str(path),
            "--name",
            "feature",
            "--",
            "/bin/sh",
            "-c",
            "echo hello",
        ]

    def test_list_tabs_for_worktree_matches_pane_cwd(self, tmp_path: Path) -> None:
        """Tabs are inventoried by pane cwd across live sessions, skipping dead ones."""
        terminal = Zellij()
        worktree = tmp_path / "wt"
        worktree.mkdir()
        sessions_output = (
            "work [Created 5s ago] \ndead [Created 1day 2h ago] (EXITED - attach to resurrect)\n"
        )
        panes = [
            {"id": 0, "is_plugin": False, "tab_id": 0, "tab_name": "main", "pane_cwd": "/other"},
            {
                "id": 1,
                "is_plugin": False,
                "tab_id": 2,
                "tab_name": "feature",
                "pane_cwd": str(worktree),
            },
            {"id": 2, "is_plugin": True, "tab_id": 3, "tab_name": "plug", "pane_cwd": ""},
        ]
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch.object(terminal, "_supports_cli_control", return_value=True),
            patch(
                "subprocess.run",
                side_effect=[
                    MagicMock(returncode=0, stdout=sessions_output),
                    MagicMock(returncode=0, stdout=json.dumps(panes)),
                ],
            ) as mock_run,
        ):
            inventory = terminal.list_tabs_for_worktree(worktree)

        assert inventory.error is None
        assert inventory.tabs == (ZellijTab(tab_id=2, session_name="work", tab_name="feature"),)
        # Only the live session is inspected
        assert mock_run.call_args_list[1].args[0] == [
            "zellij",
            "--session",
            "work",
            "action",
            "list-panes",
            "--json",
        ]

    def test_close_tabs_for_worktree_closes_by_id(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Worktree tabs are closed via close-tab-by-id."""
        monkeypatch.delenv("ZELLIJ_SESSION_NAME", raising=False)
        monkeypatch.delenv("ZELLIJ_PANE_ID", raising=False)
        terminal = Zellij()
        inventory = ZellijInventory(
            tabs=(ZellijTab(tab_id=2, session_name="work", tab_name="feature"),),
        )
        with (
            patch.object(terminal, "list_tabs_for_worktree", return_value=inventory),
            patch.object(terminal, "_current_tab", return_value=None),
            patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run,
        ):
            result = terminal.close_tabs_for_worktree(tmp_path)

        assert result.closed_tabs == inventory.tabs
        assert result.errors == ()
        assert mock_run.call_args.args[0] == [
            "zellij",
            "--session",
            "work",
            "action",
            "close-tab-by-id",
            "2",
        ]

    def test_close_tabs_for_worktree_skips_current_tab(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The tab running this process is never closed."""
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "work")
        monkeypatch.setenv("ZELLIJ_PANE_ID", "7")
        terminal = Zellij()
        inventory = ZellijInventory(
            tabs=(
                ZellijTab(tab_id=2, session_name="work", tab_name="feature"),
                ZellijTab(tab_id=5, session_name="work", tab_name="other"),
            ),
        )
        with (
            patch.object(terminal, "list_tabs_for_worktree", return_value=inventory),
            patch.object(terminal, "_current_tab", return_value=("work", 2)),
            patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run,
        ):
            result = terminal.close_tabs_for_worktree(tmp_path)

        assert result.closed_tabs == (inventory.tabs[1],)
        assert len(result.errors) == 1
        assert "current tab" in result.errors[0]
        assert len(mock_run.call_args_list) == 1

    def test_close_tabs_for_worktree_fails_safe_when_current_tab_unknown(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Inside zellij, tabs in the current session are kept if own tab lookup fails."""
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "work")
        monkeypatch.setenv("ZELLIJ_PANE_ID", "7")
        terminal = Zellij()
        inventory = ZellijInventory(
            tabs=(
                ZellijTab(tab_id=2, session_name="work", tab_name="feature"),
                ZellijTab(tab_id=3, session_name="elsewhere", tab_name="feature"),
            ),
        )
        with (
            patch.object(terminal, "list_tabs_for_worktree", return_value=inventory),
            patch.object(terminal, "_current_tab", return_value=None),
            patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run,
        ):
            result = terminal.close_tabs_for_worktree(tmp_path)

        assert result.closed_tabs == (inventory.tabs[1],)
        assert len(result.errors) == 1
        assert "could not be determined" in result.errors[0]
        assert len(mock_run.call_args_list) == 1

    def test_current_tab_resolves_own_pane(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The current tab is resolved from ZELLIJ_PANE_ID via list-panes."""
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "work")
        monkeypatch.setenv("ZELLIJ_PANE_ID", "7")
        terminal = Zellij()
        panes = [
            {"id": 1, "is_plugin": False, "tab_id": 0},
            {"id": 7, "is_plugin": False, "tab_id": 4},
        ]
        with patch(
            "subprocess.run", return_value=MagicMock(returncode=0, stdout=json.dumps(panes))
        ):
            assert terminal._current_tab() == ("work", 4)

    def test_live_session_names_handles_no_sessions(self) -> None:
        """A non-zero exit from list-sessions means there are no sessions."""
        error = subprocess.CalledProcessError(1, "zellij")
        with patch("subprocess.run", side_effect=error):
            assert Zellij._live_session_names() == []

    def test_live_session_names_preserves_spaces_and_skips_dead(self) -> None:
        """Session names with spaces parse correctly; EXITED and notice lines are skipped."""
        output = (
            "my session [Created 5s ago] \n"
            "plain [Created 2m 3s ago] \n"
            "old one [Created 1day 2h ago] (EXITED - attach to resurrect)\n"
            "No active zellij sessions found.\n"
        )
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout=output)):
            assert Zellij._live_session_names() == ["my session", "plain"]

    def test_supports_cli_control_caches_version_lookup(self) -> None:
        """The zellij version is only queried once per instance."""
        terminal = Zellij()
        with patch.object(Zellij, "_cli_version", return_value=(0, 44, 3)) as mock_version:
            assert terminal._supports_cli_control() is True
            assert terminal._supports_cli_control() is True
        mock_version.assert_called_once()


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


class TestCmux:
    """Tests for the cmux terminal.

    Evidence: `cmux --help` (cmux 0.64.14) and live verification on 2026-06-10.
    cmux is controlled via a Unix socket through its bundled CLI, so all
    operations are `cmux <command>` subprocess calls that work from any
    terminal, not just inside cmux.
    """

    def test_detect_cmux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect cmux via CMUX_WORKSPACE_ID environment variable.

        Evidence: `cmux --help` Environment section: "CMUX_WORKSPACE_ID
        Auto-set in cmux terminals." (same for CMUX_SURFACE_ID).
        """
        monkeypatch.delenv("CMUX_SURFACE_ID", raising=False)
        monkeypatch.setenv("CMUX_WORKSPACE_ID", "AB56033C-F3AB-46DC-83D2-2891F13F47C5")
        terminal = Cmux()
        assert terminal.detect() is True

    def test_detect_cmux_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Not in cmux when its environment variables are not set."""
        monkeypatch.delenv("CMUX_WORKSPACE_ID", raising=False)
        monkeypatch.delenv("CMUX_SURFACE_ID", raising=False)
        terminal = Cmux()
        assert terminal.detect() is False

    def test_is_available(self) -> None:
        """Cmux is available if the CLI is in PATH.

        Evidence: the Homebrew cask installs the CLI binary at
        /Applications/cmux.app/Contents/Resources/bin/cmux and cmux adds it
        to PATH.
        """
        terminal = Cmux()
        with patch(
            "shutil.which", return_value="/Applications/cmux.app/Contents/Resources/bin/cmux"
        ):
            assert terminal.is_available() is True

    def test_open_in_workspace_opens_tab_in_existing_workspace(self) -> None:
        r"""An existing workspace (matched by title) gets a new named tab.

        Evidence (verified live against cmux 0.64.14):
        - `cmux workspace list --json` returns {"workspaces": [{"ref":
          "workspace:N", "title": ...}]}.
        - `cmux new-surface --workspace <ref>` creates a tab and prints
          "OK surface:N pane:N workspace:N".
        - `cmux rename-tab --workspace <ref> --surface <ref> --title <t>`
          renames the tab.
        - `cmux send` has no auto-Enter; per `cmux send --help` the literal
          escape sequence \\n sends Enter. New surfaces don't accept a
          cwd/command flag, so the launch command is typed into the shell;
          the terminal buffers the input until the shell is ready (verified
          live by sending immediately after surface creation).
        """
        terminal = Cmux()
        path = Path("/some/work tree")
        workspaces_json = (
            '{"window_ref": "window:1", "workspaces": ['
            '{"ref": "workspace:2", "title": "other"},'
            '{"ref": "workspace:11", "title": "agent-cli"}]}'
        )
        with (
            patch("shutil.which", return_value="/usr/local/bin/cmux"),
            patch(
                "subprocess.run",
                side_effect=[
                    MagicMock(stdout=workspaces_json),
                    MagicMock(stdout="OK surface:32 pane:25 workspace:11\n"),
                    MagicMock(stdout="OK action=rename tab=tab:32 workspace=workspace:11\n"),
                    MagicMock(stdout="OK surface:32 workspace:11\n"),
                ],
            ) as mock_run,
        ):
            handle = terminal.open_in_workspace(
                path,
                "echo hello",
                tab_name="feature",
                workspace_name="agent-cli",
            )

        assert handle is not None
        assert handle.terminal_name == "cmux"
        assert handle.handle == "surface:32"
        assert handle.session_name == "agent-cli"
        argvs = [call.args[0] for call in mock_run.call_args_list]
        assert argvs == [
            ["cmux", "workspace", "list", "--json"],
            ["cmux", "new-surface", "--workspace", "workspace:11"],
            [
                "cmux",
                "rename-tab",
                "--workspace",
                "workspace:11",
                "--surface",
                "surface:32",
                "--title",
                "feature",
            ],
            [
                "cmux",
                "send",
                "--workspace",
                "workspace:11",
                "--surface",
                "surface:32",
                "--",
                f"cd {shlex.quote(str(path))} && echo hello\\n",
            ],
        ]

    def test_open_in_workspace_creates_missing_workspace(self) -> None:
        """A missing workspace is created with cwd, command, and a stable color.

        Evidence (verified live against cmux 0.64.14): `cmux workspace create
        --name <t> --cwd <path> --command <cmd>` prints "OK workspace:N",
        starts the initial tab's shell in --cwd, and sends the command with
        Enter after creation. `cmux workspace-action --action set-color
        --color <name>` accepts the named colors listed in its --help.
        `cmux rename-tab --workspace <ref> --title <t>` targets that
        workspace's focused tab, which is the just-created single tab.
        """
        terminal = Cmux()
        path = Path("/some/path")
        workspaces_json = '{"window_ref": "window:1", "workspaces": []}'
        with (
            patch("shutil.which", return_value="/usr/local/bin/cmux"),
            patch(
                "subprocess.run",
                side_effect=[
                    MagicMock(stdout=workspaces_json),
                    MagicMock(stdout="OK workspace:13\n"),
                    MagicMock(stdout="OK workspace:13\n"),
                    MagicMock(stdout="OK action=rename tab=tab:33 workspace=workspace:13\n"),
                ],
            ) as mock_run,
        ):
            handle = terminal.open_in_workspace(
                path,
                "echo hello",
                tab_name="feature",
                workspace_name="my-repo",
            )

        assert handle is not None
        assert handle.handle == "workspace:13"
        assert handle.session_name == "my-repo"
        argvs = [call.args[0] for call in mock_run.call_args_list]
        assert argvs == [
            ["cmux", "workspace", "list", "--json"],
            [
                "cmux",
                "workspace",
                "create",
                "--name",
                "my-repo",
                "--cwd",
                str(path),
                "--command",
                "echo hello",
            ],
            [
                "cmux",
                "workspace-action",
                "--action",
                "set-color",
                "--workspace",
                "workspace:13",
                "--color",
                "Magenta",
            ],
            ["cmux", "rename-tab", "--workspace", "workspace:13", "--title", "feature"],
        ]

    def test_workspace_color_is_deterministic(self) -> None:
        """The same workspace name always maps to the same cmux named color."""
        assert Cmux._workspace_color("my-repo") == "Magenta"
        assert Cmux._workspace_color("my-repo") == Cmux._workspace_color("my-repo")

    def test_open_tab_closes_surface_when_send_fails(self) -> None:
        """A failed `send` closes the idle tab and reports failure.

        Without this, the caller would print a success message while the
        agent never started in the new tab.
        """
        terminal = Cmux()
        send_error = subprocess.CalledProcessError(1, ["cmux", "send"])
        workspaces_json = (
            '{"window_ref": "window:1", "workspaces": [{"ref": "workspace:11", "title": "repo"}]}'
        )
        with (
            patch("shutil.which", return_value="/usr/local/bin/cmux"),
            patch(
                "subprocess.run",
                side_effect=[
                    MagicMock(stdout=workspaces_json),
                    MagicMock(stdout="OK surface:32 pane:25 workspace:11\n"),
                    send_error,
                    MagicMock(stdout="OK surface:32\n"),
                ],
            ) as mock_run,
        ):
            handle = terminal.open_in_workspace(
                Path("/some/path"),
                "echo hello",
                workspace_name="repo",
            )

        assert handle is None
        assert mock_run.call_args_list[-1].args[0] == [
            "cmux",
            "close-surface",
            "--workspace",
            "workspace:11",
            "--surface",
            "surface:32",
        ]

    def test_open_new_tab_uses_repo_root_name(self, tmp_path: Path) -> None:
        """The generic open_new_tab keeps the one-workspace-per-repo invariant.

        Worktree paths resolve to the main repo root, so tabs land in the
        repo's workspace rather than one named after the worktree directory.
        """
        terminal = Cmux()
        handle = TerminalHandle("cmux", "surface:5", "repo")
        with (
            patch(
                "agent_cli.dev.terminals.cmux.get_main_repo_root",
                return_value=Path("/repo"),
            ),
            patch.object(terminal, "open_in_workspace", return_value=handle) as mock_open,
        ):
            assert terminal.open_new_tab(tmp_path / "worktree", "echo hi", tab_name="t") is True
        mock_open.assert_called_once_with(
            tmp_path / "worktree",
            "echo hi",
            "t",
            workspace_name="repo",
        )

    def test_run_sets_cmux_quiet(self) -> None:
        """CLI calls silence cmux deprecation notices via CMUX_QUIET.

        Evidence: legacy command forms print "set CMUX_QUIET=1 to silence
        this notice", which would corrupt parsed output.
        """
        terminal = Cmux()
        with patch("subprocess.run", return_value=MagicMock(stdout="PONG\n")) as mock_run:
            assert terminal._run(["ping"]) == "PONG\n"
        assert mock_run.call_args.kwargs["env"]["CMUX_QUIET"] == "1"

    def test_open_in_workspace_returns_none_on_cli_failure(self) -> None:
        """A failing workspace listing aborts immediately, without a create attempt.

        Listing failure (e.g. app not running) is distinct from "workspace
        not found": creating anyway would fail too, or duplicate a workspace
        the listing could not see.
        """
        terminal = Cmux()
        error = subprocess.CalledProcessError(1, ["cmux", "workspace", "list", "--json"])
        with (
            patch("shutil.which", return_value="/usr/local/bin/cmux"),
            patch("subprocess.run", side_effect=[error]) as mock_run,
        ):
            handle = terminal.open_in_workspace(
                Path("/some/path"),
                "echo hello",
                workspace_name="my-repo",
            )
        assert handle is None
        assert mock_run.call_count == 1


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

    def test_detect_current_terminal_cmux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect current terminal as cmux when no multiplexer is running."""
        monkeypatch.delenv("TMUX", raising=False)
        monkeypatch.delenv("ZELLIJ", raising=False)
        monkeypatch.setenv("CMUX_WORKSPACE_ID", "AB56033C-F3AB-46DC-83D2-2891F13F47C5")
        terminal = detect_current_terminal()
        assert terminal is not None
        assert terminal.name == "cmux"

    def test_detect_tmux_wins_inside_cmux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tmux running inside a cmux tab is detected as tmux (innermost wins)."""
        monkeypatch.setenv("TMUX", "/run/user/1000/tmux")
        monkeypatch.setenv("CMUX_WORKSPACE_ID", "AB56033C-F3AB-46DC-83D2-2891F13F47C5")
        terminal = detect_current_terminal()
        assert terminal is not None
        assert terminal.name == "tmux"

    def test_get_available_terminals(self) -> None:
        """Get available terminals returns list."""
        terminals = get_available_terminals()
        assert isinstance(terminals, list)
