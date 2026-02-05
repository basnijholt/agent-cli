"""Tests for editor adapters."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agent_cli.dev.editors import (
    Editor,
    detect_current_editor,
    get_all_editors,
    get_available_editors,
    get_editor,
)
from agent_cli.dev.editors.emacs import Emacs
from agent_cli.dev.editors.jetbrains import PyCharm
from agent_cli.dev.editors.neovim import Neovim
from agent_cli.dev.editors.vim import Vim
from agent_cli.dev.editors.vscode import VSCode


class TestEditorBase:
    """Tests for Editor base class."""

    def test_detect_with_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect editor via environment variable."""
        monkeypatch.setenv("NVIM", "v0.9.0")
        editor = Neovim()
        assert editor.detect() is True

    def test_detect_with_term_program(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect editor via TERM_PROGRAM."""
        monkeypatch.setenv("TERM_PROGRAM", "vscode")
        editor = VSCode()
        assert editor.detect() is True

    def test_detect_term_program_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TERM_PROGRAM detection is case insensitive."""
        monkeypatch.setenv("TERM_PROGRAM", "VSCode")
        editor = VSCode()
        assert editor.detect() is True

    def test_is_available(self) -> None:
        """Editor is available if command in PATH."""
        editor = VSCode()
        with patch("shutil.which", return_value="/usr/bin/code"):
            assert editor.is_available() is True

    def test_is_available_alt_command(self) -> None:
        """Editor is available via alt command."""
        editor = VSCode()
        with patch(
            "shutil.which",
            side_effect=lambda cmd: "/usr/bin/code-insiders" if cmd == "code-insiders" else None,
        ):
            assert editor.is_available() is True

    def test_open_command(self) -> None:
        """Generate open command."""
        editor = VSCode()
        with patch("shutil.which", return_value="/usr/bin/code"):
            cmd = editor.open_command(Path("/some/path"))
        assert cmd == ["/usr/bin/code", "/some/path"]

    def test_open_command_not_installed(self) -> None:
        """Raise error when editor not installed."""
        editor = VSCode()
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(RuntimeError, match="vscode is not installed"),
        ):
            editor.open_command(Path("/some/path"))

    def test_repr(self) -> None:
        """String representation includes name and status."""
        editor = VSCode()
        with patch("shutil.which", return_value=None):
            assert "vscode" in repr(editor)
            assert "not installed" in repr(editor)


class TestTerminalEditors:
    """Tests for terminal-based editors (vim, neovim, nano)."""

    def test_vim_open_command_uses_cd_pattern(self) -> None:
        """Vim uses cd && vim . pattern."""
        editor = Vim()
        with patch("shutil.which", return_value="/usr/bin/vim"):
            cmd = editor.open_command(Path("/some/path"))
        assert cmd == ["sh", "-c", 'cd "/some/path" && /usr/bin/vim .']

    def test_neovim_open_command_uses_cd_pattern(self) -> None:
        """Neovim uses cd && nvim . pattern."""
        editor = Neovim()
        with patch("shutil.which", return_value="/usr/bin/nvim"):
            cmd = editor.open_command(Path("/some/path"))
        assert cmd == ["sh", "-c", 'cd "/some/path" && /usr/bin/nvim .']

    def test_neovim_detects_nvim_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Neovim detects NVIM environment variable."""
        monkeypatch.setenv("NVIM", "/run/user/1000/nvim.sock")
        editor = Neovim()
        assert editor.detect() is True

    def test_vim_no_detection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Vim does NOT detect via VIM env var - it has no integrated terminal.

        VIM/VIMRUNTIME are used BY vim to locate runtime files, NOT to indicate
        running inside vim. Vim has no integrated terminal, so detect() always
        returns False.
        """
        # Even with VIM set, detection should return False
        monkeypatch.setenv("VIM", "/usr/share/vim")
        editor = Vim()
        assert editor.detect() is False


class TestEmacsEditor:
    """Tests for Emacs editor."""

    def test_emacs_background_mode(self) -> None:
        """Standalone emacs runs in background."""
        editor = Emacs()
        with patch("shutil.which", return_value="/usr/bin/emacs"):
            cmd = editor.open_command(Path("/some/path"))
        assert cmd == ["sh", "-c", '/usr/bin/emacs "/some/path" &']

    def test_emacsclient_uses_n_flag(self) -> None:
        """Emacsclient uses -n flag."""
        editor = Emacs()
        with patch(
            "shutil.which",
            side_effect=lambda cmd: "/usr/bin/emacsclient" if cmd == "emacsclient" else None,
        ):
            cmd = editor.open_command(Path("/some/path"))
        assert cmd == ["/usr/bin/emacsclient", "-n", "/some/path"]

    def test_emacs_detects_inside_emacs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Emacs detects INSIDE_EMACS variable."""
        monkeypatch.setenv("INSIDE_EMACS", "29.1,comint")
        editor = Emacs()
        assert editor.detect() is True


class TestJetBrainsEditors:
    """Tests for JetBrains IDE editors."""

    def test_pycharm_detects_jediterm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PyCharm detects JetBrains-JediTerm terminal.

        Source: https://github.com/JetBrains/jediterm/issues/253
        """
        monkeypatch.setenv("TERMINAL_EMULATOR", "JetBrains-JediTerm")
        editor = PyCharm()
        assert editor.detect() is True


class TestRegistry:
    """Tests for editor registry functions."""

    def test_get_all_editors(self) -> None:
        """Get all registered editors."""
        editors = get_all_editors()
        assert len(editors) > 0
        assert all(isinstance(e, Editor) for e in editors)

    def test_get_all_editors_cached(self) -> None:
        """Editor instances are cached."""
        editors1 = get_all_editors()
        editors2 = get_all_editors()
        assert editors1[0] is editors2[0]

    def test_get_editor_by_name(self) -> None:
        """Get editor by name."""
        editor = get_editor("vscode")
        assert editor is not None
        assert editor.name == "vscode"

    def test_get_editor_by_command(self) -> None:
        """Get editor by command name."""
        editor = get_editor("code")
        assert editor is not None
        assert editor.command == "code"

    def test_get_editor_case_insensitive(self) -> None:
        """Editor lookup is case insensitive."""
        editor = get_editor("VSCODE")
        assert editor is not None
        assert editor.name == "vscode"

    def test_get_editor_not_found(self) -> None:
        """Return None for unknown editor."""
        editor = get_editor("nonexistent")
        assert editor is None

    def test_detect_current_editor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Detect current editor from environment."""
        monkeypatch.setenv("TERM_PROGRAM", "vscode")
        editor = detect_current_editor()
        assert editor is not None
        assert editor.name == "vscode"

    def test_get_available_editors(self) -> None:
        """Get available editors returns list."""
        editors = get_available_editors()
        assert isinstance(editors, list)
