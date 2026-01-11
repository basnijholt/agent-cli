"""Tests for terminal adapters."""

from __future__ import annotations

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
from agent_cli.dev.terminals.tmux import Tmux
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
            patch("shutil.which", return_value="/usr/bin/tmux"),
        ):
            result = terminal.open_new_tab(Path("/some/path"), "echo hello", tab_name="test")

        assert result is True
        # Check that tmux new-window was called
        call_args = mock_run.call_args
        assert "new-window" in call_args[0][0]


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
