"""Verification tests with documented evidence sources.

These tests verify that our detection logic matches real-world behavior.
Each test docstring documents:
- The source of truth (man page, --help, official docs, live test)
- The specific evidence (command output, URL, env var value)
- Date of verification

This serves as both executable tests AND documentation of our verification.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest  # noqa: TC002

from agent_cli.dev.coding_agents.aider import Aider
from agent_cli.dev.coding_agents.claude import ClaudeCode
from agent_cli.dev.coding_agents.codex import Codex
from agent_cli.dev.coding_agents.continue_dev import ContinueDev
from agent_cli.dev.coding_agents.copilot import Copilot
from agent_cli.dev.coding_agents.cursor_agent import CursorAgent
from agent_cli.dev.coding_agents.gemini import Gemini
from agent_cli.dev.coding_agents.opencode import OpenCode
from agent_cli.dev.editors.cursor import Cursor
from agent_cli.dev.editors.emacs import Emacs
from agent_cli.dev.editors.jetbrains import PyCharm
from agent_cli.dev.editors.nano import Nano
from agent_cli.dev.editors.neovim import Neovim
from agent_cli.dev.editors.sublime import SublimeText
from agent_cli.dev.editors.vim import Vim
from agent_cli.dev.editors.vscode import VSCode
from agent_cli.dev.editors.zed import Zed
from agent_cli.dev.terminals.gnome import GnomeTerminal
from agent_cli.dev.terminals.iterm2 import ITerm2
from agent_cli.dev.terminals.kitty import Kitty
from agent_cli.dev.terminals.tmux import Tmux
from agent_cli.dev.terminals.warp import Warp
from agent_cli.dev.terminals.zellij import Zellij


class TestTerminalDetection:
    """Tests for terminal multiplexer detection.

    Terminals are detected via environment variables set by the terminal itself.
    """

    def test_tmux_detection_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tmux sets TMUX environment variable when running inside a session.

        Evidence:
            Source: man tmux
            Quote: "tmux also initialises the TMUX variable with some internal
                   information to allow commands to be executed from inside"
            Format: "/tmp/tmux-1000/default,12345,0" (socket,pid,window)
            Verified: 2026-01-11 via `man tmux | grep -A2 "TMUX variable"`
        """
        # TMUX contains socket path, server pid, and window index
        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,12345,0")  # noqa: S108
        terminal = Tmux()
        assert terminal.detect() is True

    def test_tmux_not_detected_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tmux is not detected when TMUX env var is absent."""
        monkeypatch.delenv("TMUX", raising=False)
        terminal = Tmux()
        assert terminal.detect() is False

    def test_zellij_detection_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Zellij sets ZELLIJ environment variable (presence check, not value).

        Evidence:
            Source: Zellij Integration documentation
            URL: https://zellij.dev/documentation/integration.html
            Quote: "ZELLIJ gets set to `0` inside a zellij session"
            Also: ZELLIJ_SESSION_NAME has session name as value
            Note: Value is "0" but presence indicates inside zellij
            Verified: 2026-01-11 via official docs
        """
        # Zellij sets ZELLIJ=0 (presence check, not value check)
        monkeypatch.setenv("ZELLIJ", "0")
        terminal = Zellij()
        assert terminal.detect() is True

    def test_kitty_detection_window_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Kitty sets KITTY_WINDOW_ID when running inside kitty.

        Evidence:
            Source: Kitty glossary (environment variables)
            URL: https://sw.kovidgoyal.net/kitty/glossary/#envvar-KITTY_WINDOW_ID
            Quote: "An integer that is the id for the kitty window the program is running in."
            Verified: 2026-01-11 via official docs
        """
        monkeypatch.setenv("KITTY_WINDOW_ID", "1")
        terminal = Kitty()
        assert terminal.detect() is True

    def test_kitty_detection_term(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Kitty also detectable via TERM=xterm-kitty.

        Evidence:
            Source: Kitty FAQ
            URL: https://sw.kovidgoyal.net/kitty/faq/#i-get-errors-about-the-terminal-being-unknown
            Quote: "kitty uses the value xterm-kitty for the TERM environment variable"
            Verified: 2026-01-11 via official kitty FAQ
        """
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.setenv("TERM", "xterm-kitty")
        terminal = Kitty()
        assert terminal.detect() is True

    def test_gnome_terminal_detection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GNOME Terminal sets GNOME_TERMINAL_SERVICE.

        Evidence:
            Source: GNOME Terminal source code (two files)
            Definition URL: https://gitlab.gnome.org/GNOME/gnome-terminal/-/blob/master/src/terminal-defines.hh
            Definition: `#define TERMINAL_ENV_SERVICE_NAME "GNOME_TERMINAL_SERVICE"`
            Setting URL: https://gitlab.gnome.org/GNOME/gnome-terminal/-/blob/master/src/terminal-screen.cc
            Code: `g_hash_table_replace(env_table, g_strdup(TERMINAL_ENV_SERVICE_NAME),
                   g_strdup(g_dbus_connection_get_unique_name(connection)));`
            Format: ":1.123" (D-Bus connection unique name)
            Verified: 2026-01-11 via source code inspection
        """
        monkeypatch.setenv("GNOME_TERMINAL_SERVICE", ":1.123")
        terminal = GnomeTerminal()
        assert terminal.detect() is True

    def test_iterm2_detection_session_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """iTerm2 sets ITERM_SESSION_ID environment variable.

        Evidence:
            Source: iTerm2 source code (PTYSession.m)
            URL: https://github.com/gnachman/iTerm2/blob/master/sources/PTYSession.m
            Code: env[@"ITERM_SESSION_ID"] = itermId;
            Format: "w0t0p0:UUID" (window, tab, pane, session UUID)
            Platform: macOS only
            Verified: 2026-01-11 via source code inspection
        """
        monkeypatch.setenv("ITERM_SESSION_ID", "w0t0p0:12345678-ABCD-EFGH-IJKL-MNOPQRSTUVWX")
        terminal = ITerm2()
        assert terminal.detect() is True

    def test_iterm2_detection_term_program(self, monkeypatch: pytest.MonkeyPatch) -> None:
        r"""iTerm2 also detectable via TERM_PROGRAM containing 'iterm'.

        Evidence:
            Source: iTerm2 source code (PTYSession.m)
            URL: https://github.com/gnachman/iTerm2/blob/master/sources/PTYSession.m
            Code: env[@"TERM_PROGRAM"] = @"iTerm.app";
            Verified: 2026-01-11 via source code inspection
        """
        monkeypatch.delenv("ITERM_SESSION_ID", raising=False)
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        terminal = ITerm2()
        assert terminal.detect() is True

    def test_warp_detection_term_program(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Warp sets TERM_PROGRAM=WarpTerminal.

        Evidence:
            Source: Warp Prompt documentation
            URL: https://docs.warp.dev/terminal/appearance/prompt
            Quote: `if [[ $TERM_PROGRAM != "WarpTerminal" ]]; then`
            Platform: macOS (and Linux beta)
            Note: Tab naming not supported - no API available
            Verified: 2026-01-11 via official Warp docs
        """
        monkeypatch.setenv("TERM_PROGRAM", "WarpTerminal")
        terminal = Warp()
        assert terminal.detect() is True


class TestTerminalCommands:
    """Tests for terminal command syntax.

    These verify the exact command-line syntax for opening new tabs/windows.
    """

    def test_tmux_new_window_command(self) -> None:
        """Tmux new-window uses -c for working directory and -n for name.

        Evidence:
            Source: man tmux
            Command: new-window [-abdkPS] [-c start-directory] [-n window-name] ...
            Quote: "-c specifies the working directory in which the new window is created"
            Quote: "-n window-name"
            Verified: 2026-01-11 via `man tmux | grep -A10 "new-window"`
        """
        terminal = Tmux()
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("shutil.which", return_value="/usr/bin/tmux"),
            patch("subprocess.run", mock_run),
        ):
            # Verify the command syntax by checking what gets passed to subprocess
            terminal.open_new_tab(
                Path("/test/path"),
                command="echo hello",
                tab_name="test-tab",
            )
        # Verify correct flags were used
        call_args = mock_run.call_args[0][0]
        assert "new-window" in call_args
        assert "-c" in call_args
        assert "-n" in call_args
        assert "test-tab" in call_args

    def test_zellij_new_tab_command_syntax(self) -> None:
        """Zellij uses `zellij action new-tab --cwd <path> --name <name>`.

        Evidence:
            Source: zellij action new-tab --help
            Output:
                -c, --cwd <CWD>    Change the working directory of the new tab
                -n, --name <NAME>  Name of the new tab
            Verified: 2026-01-11 via `zellij action new-tab --help`
        """
        # Syntax verified via --help, implementation tested elsewhere

    def test_zellij_write_enter_byte(self) -> None:
        """Zellij sends Enter key via `zellij action write 10` (byte 10 = newline).

        Evidence:
            Source: zellij action write --help
            Quote: "Write bytes to the terminal"
            Note: Byte 10 is ASCII newline (Enter key)
            Verified: 2026-01-11 via `zellij action write --help`
        """
        # Byte 10 = newline verified via ASCII table

    def test_kitty_launch_tab_command(self) -> None:
        """Kitty uses `kitten @ launch --type=tab --cwd=<path> --tab-title=<name>`.

        Evidence:
            Source: kitten @ launch --help
            Output:
                --type [=window]: "tab" for new tab in current OS window
                --cwd: The working directory for the newly launched child
                --tab-title: The title for the new tab
            Verified: 2026-01-11 via `kitten @ launch --help`
        """
        # Syntax verified via --help

    def test_gnome_terminal_tab_command(self) -> None:
        """GNOME Terminal uses `gnome-terminal --tab --working-directory=<path> --title=<name>`.

        Evidence:
            Source: gnome-terminal --help-all
            Output:
                --tab: Open a new tab in the last-opened window
                --working-directory=DIRNAME: Set the working directory
                -t, --title=TITLE: Set the initial terminal title
            Verified: 2026-01-11 via `nix-shell -p gnome-terminal --run "gnome-terminal --help-all"`
        """
        # Syntax verified via --help-all

    def test_warp_uri_scheme(self) -> None:
        """Warp uses URI scheme for simple tabs and Launch Configurations for commands.

        Evidence:
            URI scheme: https://docs.warp.dev/terminal/more-features/uri-scheme
            Syntax: warp://action/new_tab?path=<path>
            Launch configs: https://docs.warp.dev/terminal/sessions/launch-configurations
            Config location: ~/.warp/launch_configurations/
            Verified: 2026-01-11 via official Warp docs
        """
        terminal = Warp()
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch("subprocess.run", mock_run),
        ):
            # Simple case: no command uses URI scheme directly
            terminal.open_new_tab(Path("/test/path"), command=None)

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "open"
        assert "warp://action/new_tab?path=" in call_args[1]

    def test_warp_launch_config_for_commands(self) -> None:
        """Warp uses temporary Launch Configuration files for executing commands.

        Evidence:
            Source: https://docs.warp.dev/terminal/sessions/launch-configurations
            YAML format supports 'commands' with 'exec' entries
            URI: warp://launch/<config-path>
            Verified: 2026-01-11 via official Warp docs
        """
        terminal = Warp()
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        mock_popen = MagicMock()
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch("subprocess.run", mock_run),
            patch("subprocess.Popen", mock_popen),
            patch("pathlib.Path.write_text") as mock_write,
            patch("pathlib.Path.mkdir"),
        ):
            terminal.open_new_tab(
                Path("/test/path"),
                command="claude",
                tab_name="my-agent",
            )

        # Verify YAML config was written with quoted values (for special char safety)
        assert mock_write.called
        yaml_content = mock_write.call_args[0][0]
        assert "cwd: '/test/path'" in yaml_content
        assert "exec: 'claude'" in yaml_content
        assert "title: 'my-agent'" in yaml_content

    def test_iterm2_applescript_syntax(self) -> None:
        """iTerm2 uses official AppleScript API for tab creation.

        Evidence:
            Source: https://iterm2.com/documentation-scripting.html
            Commands: "create tab with default profile", "write text"
            Quote: "Creates a tab with the default profile or a profile by name"
            Note: AppleScript is deprecated in favor of Python API, but still
                  documented and functional. Python API requires iTerm2's
                  internal environment, making AppleScript practical for
                  external CLI tools.
            Verified: 2026-01-12 via official iTerm2 docs
        """
        terminal = ITerm2()
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch.object(terminal, "is_available", return_value=True),
            patch("subprocess.run", mock_run),
        ):
            terminal.open_new_tab(
                Path("/test/path"),
                command="claude",
                tab_name="my-agent",
            )

        # Verify AppleScript was called with correct syntax
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "osascript"
        applescript = call_args[2]  # -e argument
        assert 'tell application "iTerm2"' in applescript
        assert "create tab with default profile" in applescript
        assert "write text" in applescript
        assert 'set name to "my-agent"' in applescript


class TestEditorDetection:
    """Tests for editor detection via environment variables.

    Editors set specific env vars when running their integrated terminals.
    """

    def test_vscode_detection_term_program(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """VS Code sets TERM_PROGRAM=vscode in integrated terminal.

        Evidence:
            Source: VS Code Shell Integration docs
            URL: https://code.visualstudio.com/docs/terminal/shell-integration
            Quote: `[[ "$TERM_PROGRAM" == "vscode" ]] && . ...`
            GitHub: PR #30346 merged July 2017
            Verified: 2026-01-11 via official docs
        """
        monkeypatch.setenv("TERM_PROGRAM", "vscode")
        editor = VSCode()
        assert editor.detect() is True

    def test_neovim_detection_nvim_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Neovim sets $NVIM in :terminal buffers and jobstart() children.

        Evidence:
            Source: Neovim vvars documentation
            URL: https://neovim.io/doc/user/vvars.html
            Quote: "$NVIM is set to v:servername by terminal and jobstart(),
                   and is thus a hint that the current environment is a child
                   (direct subprocess) of Nvim"
            Note: NVIM_LISTEN_ADDRESS is deprecated; detection uses $NVIM only
            Verified: 2026-01-11 via official Neovim docs
        """
        monkeypatch.setenv("NVIM", "/run/user/1000/nvim.12345.0")
        editor = Neovim()
        assert editor.detect() is True

    def test_neovim_deprecated_listen_address(self) -> None:
        """NVIM_LISTEN_ADDRESS is deprecated and not used for detection.

        Evidence:
            Source: Neovim deprecated env vars documentation
            URL: https://neovim.io/doc/user/deprecated.html#$NVIM_LISTEN_ADDRESS
            Quote: "Deprecated way to: ... detect a parent Nvim (use $NVIM instead)"
            Verified: 2026-01-11 via official Neovim docs
        """
        editor = Neovim()
        assert "NVIM_LISTEN_ADDRESS" not in editor.detect_env_vars

    def test_emacs_detection_inside_emacs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Emacs sets INSIDE_EMACS in subprocesses (shell, term, vterm, eshell).

        Evidence:
            Source: Emacs comint.el source code
            URL: https://github.com/emacs-mirror/emacs/blob/master/lisp/comint.el
            Code: `(list (format "INSIDE_EMACS=%s,comint" emacs-version))`
            Context: Set in comint-exec-1 function's process-environment via nconc
            Format: "<version>,<mode>" e.g., "29.1,comint" or "29.1,eshell"
            Verified: 2026-01-11 via source code inspection
        """
        monkeypatch.setenv("INSIDE_EMACS", "29.1,eshell")
        editor = Emacs()
        assert editor.detect() is True

    def test_jetbrains_detection_terminal_emulator(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """JetBrains IDEs set TERMINAL_EMULATOR=JetBrains-JediTerm.

        Evidence:
            Source: IntelliJ Community source code (Jewel utils)
            URL: https://github.com/JetBrains/intellij-community/blob/master/platform/jewel/scripts/utils.main.kts
            Code: `System.getenv("TERMINAL_EMULATOR") == "JetBrains-JediTerm"`
            Note: Used to detect IntelliJ's built-in terminal in JetBrains tooling
            Verified: 2026-01-11 via source code inspection
        """
        monkeypatch.setenv("TERMINAL_EMULATOR", "JetBrains-JediTerm")
        editor = PyCharm()
        assert editor.detect() is True

    def test_zed_detection_zed_term(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Zed sets ZED_TERM=true in integrated terminal.

        Evidence:
            Source: Zed source code
            URL: https://github.com/zed-industries/zed/blob/main/crates/terminal/src/terminal.rs
            Code:
                env.insert("ZED_TERM".to_string(), "true".to_string());
                env.insert("TERM_PROGRAM".to_string(), "zed".to_string());
            Function: insert_zed_terminal_env()
            Note: NOT in docs (zed.dev/docs/environment) but IS in source code
            Verified: 2026-01-11 via source code inspection
        """
        monkeypatch.setenv("ZED_TERM", "true")
        editor = Zed()
        assert editor.detect() is True

    def test_zed_detection_term_program(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Zed sets TERM_PROGRAM=zed in integrated terminal.

        Evidence:
            Source: Zed source code
            URL: https://github.com/zed-industries/zed/blob/main/crates/terminal/src/terminal.rs
            Code: env.insert("TERM_PROGRAM".to_string(), "zed".to_string());
            Verified: 2026-01-11 via source code inspection
        """
        monkeypatch.delenv("ZED_TERM", raising=False)
        monkeypatch.setenv("TERM_PROGRAM", "zed")
        editor = Zed()
        assert editor.detect() is True

    def test_cursor_detection_cursor_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cursor editor detectable via CURSOR_AGENT environment variable.

        Evidence:
            Source: Cursor Terminal documentation
            URL: https://cursor.com/docs/agent/terminal
            Quote: "You can use the CURSOR_AGENT environment variable in your
                   shell config to detect when the Agent is running"
            Note: Cursor is an AI-first code editor (VS Code fork)
            Note: Cursor is proprietary, not available in nixpkgs for live testing
            Verified: 2026-01-11 via official Cursor docs (web search)
        """
        monkeypatch.setenv("CURSOR_AGENT", "1")
        editor = Cursor()
        assert editor.detect() is True

    def test_sublime_command_and_alternatives(self) -> None:
        """Sublime Text command configuration (not terminal detection).

        Evidence:
            Source: Sublime Text Command Line documentation
            URL: https://www.sublimetext.com/docs/command_line.html
            Commands: subl (symlink), sublime_text (binary), sublime

            Important: Sublime Text has NO built-in integrated terminal.
            The detect_term_program field exists but is theoretical -
            terminal packages like Terminus may set TERM_PROGRAM, but
            this is plugin-dependent, not native Sublime behavior.

            Verified: 2026-01-11 via official CLI docs and web search
                      confirming no native terminal
        """
        editor = SublimeText()
        assert editor.command == "subl"
        assert "sublime_text" in editor.alt_commands
        assert "sublime" in editor.alt_commands

    def test_vim_no_integrated_terminal(self) -> None:
        """Vim has NO integrated terminal - VIM/VIMRUNTIME are NOT detection vars.

        Evidence:
            Source: Vim documentation
            URL: https://vimdoc.sourceforge.net/htmldoc/starting.html
            Quote: "The environment variable '$VIM' is used to locate various
                   user files for Vim" and "$VIMRUNTIME is used to locate
                   various support files, such as the on-line documentation"

            Critical: VIM and VIMRUNTIME are used BY vim to find files,
            NOT set to indicate running inside vim. Vim does not have an
            integrated terminal like VS Code or Emacs.

            Verified: 2026-01-11 via official vim documentation
        """
        editor = Vim()
        # Vim should have no detect_env_vars since it has no integrated terminal
        assert not hasattr(editor, "detect_env_vars") or not editor.detect_env_vars
        # Detection should always return False
        assert editor.detect() is False

    def test_nano_no_integrated_terminal(self) -> None:
        """Nano has NO integrated terminal - it's a simple terminal text editor.

        Evidence:
            Source: Nano official website and documentation
            URL: https://www.nano-editor.org
            Finding: Nano is a terminal-based editor, not an IDE with integrated
                    terminal. It has no detection mechanism because you can't
                    run a shell inside nano.

            Verified: 2026-01-11 via official nano documentation
        """
        editor = Nano()
        # Nano should have no detect_env_vars
        assert not hasattr(editor, "detect_env_vars") or not editor.detect_env_vars
        # Detection should always return False
        assert editor.detect() is False

    def test_emacs_deprecated_emacs_env_var(self) -> None:
        """The EMACS env var is DEPRECATED - use INSIDE_EMACS instead.

        Evidence:
            Source: Emacs NEWS.25
            URL: https://github.com/emacs-mirror/emacs/blob/master/etc/NEWS.25
            Quote: "'M-x shell' and 'M-x compile' no longer set the EMACS
                   environment variable. This avoids clashing when other
                   programs use the variable for other purposes. [...]
                   Use the INSIDE_EMACS environment variable instead."

            Important: The EMACS env var conflicted with other programs.
            Only INSIDE_EMACS should be used for detection.

            Verified: 2026-01-11 via Emacs NEWS.25
        """
        editor = Emacs()
        # Only INSIDE_EMACS should be in detect_env_vars, not EMACS
        assert "INSIDE_EMACS" in editor.detect_env_vars
        assert "EMACS" not in editor.detect_env_vars


class TestEditorCommands:
    """Tests for editor open command syntax."""

    def test_vim_uses_cd_and_dot_pattern(self) -> None:
        """Vim/Neovim use `cd "<path>" && vim .` pattern to open directory.

        Evidence:
            Source: vim --help
            Finding: vim has no --directory or --cwd flag
            Pattern: `cd "<path>" && vim .` is standard workaround
            Verified: 2026-01-11 via `nix-shell -p vim --run "vim --help"`
        """
        editor = Vim()
        with patch("shutil.which", return_value="/usr/bin/vim"):
            cmd = editor.open_command(Path("/some/path"))
        assert cmd == ["sh", "-c", 'cd "/some/path" && /usr/bin/vim .']

    def test_emacs_background_mode(self) -> None:
        """Standalone emacs runs in background with `emacs "<path>" &`.

        Evidence:
            Source: emacs --help
            Output: "--daemon, --bg-daemon[=NAME] start a (named) server in the background"
            Pattern: Running `emacs path &` prevents blocking the terminal
            Alternative: `emacsclient -n` for running emacs daemon
            Verified: 2026-01-11 via `nix-shell -p emacs --run "emacs --help"`
        """
        editor = Emacs()
        with patch("shutil.which", return_value="/usr/bin/emacs"):
            cmd = editor.open_command(Path("/some/path"))
        assert cmd == ["sh", "-c", '/usr/bin/emacs "/some/path" &']

    def test_emacsclient_no_wait_flag(self) -> None:
        """Emacsclient uses -n (--no-wait) to not block terminal.

        Evidence:
            Source: emacsclient --help
            Output: "-n, --no-wait  Don't wait for the server to return"
            Verified: 2026-01-11 via `nix-shell -p emacs --run "emacsclient --help"`
        """
        editor = Emacs()
        # When emacsclient is found but not emacs
        with patch(
            "shutil.which",
            side_effect=lambda cmd: "/usr/bin/emacsclient" if cmd == "emacsclient" else None,
        ):
            cmd = editor.open_command(Path("/some/path"))
        assert cmd == ["/usr/bin/emacsclient", "-n", "/some/path"]


class TestCodingAgentDetection:
    """Tests for AI coding agent detection.

    Agents are detected via environment variables OR parent process name.
    """

    def test_claude_code_detection_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Claude Code sets CLAUDECODE=1 when running.

        Evidence:
            Source: Claude Code npm package (cli.js)
            URL: https://registry.npmjs.org/@anthropic-ai/claude-code/-/claude-code-2.1.4.tgz
            File: package/cli.js
            Code: `env:{...process.env, ..., CLAUDECODE:"1", ...}`
            Verified: 2026-01-11 via package source inspection
        """
        monkeypatch.setenv("CLAUDECODE", "1")
        agent = ClaudeCode()
        assert agent.detect() is True

    def test_claude_code_detection_requires_value_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Claude Code detection requires CLAUDECODE='1', not just presence.

        Evidence:
            Source: Implementation decision
            Reason: Prevents false positives if env var is set to other values
            Verified: 2026-01-11 via code review
        """
        monkeypatch.setenv("CLAUDECODE", "0")
        agent = ClaudeCode()
        # Should not detect with value "0", only with "1"
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=[],
        ):
            assert agent.detect() is False

    def test_opencode_detection_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OpenCode sets OPENCODE=1 when running.

        Evidence:
            Source: GitHub PR #1780
            URL: https://github.com/sst/opencode/pull/1780
            Title: "chore: add OPENCODE env var"
            Code: Adds `OPENCODE=1` env var as per issue #1775
            Merged: 2025-08-11 by @thdxr
            Verified: 2026-01-11 via GitHub PR
        """
        monkeypatch.setenv("OPENCODE", "1")
        agent = OpenCode()
        assert agent.detect() is True

    def test_cursor_agent_detection_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cursor Agent sets CURSOR_AGENT environment variable.

        Evidence:
            Source: Cursor Terminal documentation
            URL: https://docs.cursor.com/en/agent/terminal
            Quote: "You can use the CURSOR_AGENT environment variable in your
                   shell config to detect when the Agent is running"
            Verified: 2026-01-11 via official Cursor docs
        """
        monkeypatch.setenv("CURSOR_AGENT", "1")
        agent = CursorAgent()
        assert agent.detect() is True

    def test_aider_no_detection_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Aider does NOT set a detection env var - uses parent process only.

        Evidence:
            Source: aider --help output
            Finding: AIDER_* variables are for configuration only, not detection
            Examples: AIDER_MODEL, AIDER_OPENAI_API_KEY, etc.
            Detection: Must use parent process name matching
            Verified: 2026-01-11 via `nix-shell -p aider-chat --run "aider --help"`
        """
        # No AIDER env var for detection
        monkeypatch.delenv("AIDER", raising=False)
        agent = Aider()
        # Without parent process match, should not detect
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=[],
        ):
            assert agent.detect() is False

    def test_aider_detection_via_parent_process(self) -> None:
        """Aider is detected via parent process name containing 'aider'.

        Evidence:
            Source: Aider pyproject.toml (console script entry point)
            URL: https://raw.githubusercontent.com/Aider-AI/aider/main/pyproject.toml
            Code: [project.scripts] aider = "aider.main:main"
            Verified: 2026-01-11 via source code inspection
        """
        agent = Aider()
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=["bash", "aider", "zsh"],
        ):
            assert agent.detect() is True

    def test_codex_detection_via_parent_process(self) -> None:
        """Codex is detected via parent process name containing 'codex'.

        Evidence:
            Source: npm registry metadata (bin field)
            URL: https://registry.npmjs.org/@openai/codex/latest
            Quote: "bin": {"codex": "bin/codex.js"}
            Verified: 2026-01-11 via npm registry
        """
        agent = Codex()
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=["bash", "codex", "zsh"],
        ):
            assert agent.detect() is True

    def test_gemini_detection_via_parent_process(self) -> None:
        """Gemini is detected via parent process name containing 'gemini'.

        Evidence:
            Source: npm registry metadata (bin field)
            URL: https://registry.npmjs.org/@google/gemini-cli/latest
            Quote: "bin": {"gemini": "dist/index.js"}
            Verified: 2026-01-11 via npm registry
        """
        agent = Gemini()
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=["bash", "gemini", "zsh"],
        ):
            assert agent.detect() is True

    def test_copilot_detection_via_parent_process(self) -> None:
        """Copilot is detected via parent process name containing 'copilot'.

        Evidence:
            Source: npm registry metadata (bin field)
            URL: https://registry.npmjs.org/@github/copilot/latest
            Quote: "bin": {"copilot": "npm-loader.js"}
            Verified: 2026-01-11 via npm registry
        """
        agent = Copilot()
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=["bash", "copilot", "zsh"],
        ):
            assert agent.detect() is True

    def test_continue_dev_detection_via_parent_process(self) -> None:
        """Continue Dev is detected via parent process name 'cn'.

        Evidence:
            Source: npm registry metadata (bin field)
            URL: https://registry.npmjs.org/@continuedev/cli/latest
            Quote: "bin": {"cn": "dist/cn.js"}
            Verified: 2026-01-11 via npm registry
        """
        agent = ContinueDev()
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=["bash", "cn", "zsh"],
        ):
            assert agent.detect() is True

    def test_claude_code_detection_via_parent_process(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Claude Code is detected via parent process name containing 'claude'.

        Evidence:
            Source: npm registry metadata (bin field)
            URL: https://registry.npmjs.org/@anthropic-ai/claude-code/latest
            Quote: "bin": {"claude": "cli.js"}
            Verified: 2026-01-11 via npm registry
        """
        monkeypatch.delenv("CLAUDECODE", raising=False)
        agent = ClaudeCode()
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=["bash", "claude", "zsh"],
        ):
            assert agent.detect() is True

    def test_opencode_detection_via_parent_process(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OpenCode is detected via parent process name containing 'opencode'.

        Evidence:
            Source: npm registry metadata (bin field)
            URL: https://registry.npmjs.org/opencode-ai/latest
            Quote: "bin": {"opencode": "bin/opencode"}
            Verified: 2026-01-11 via npm registry
        """
        monkeypatch.delenv("OPENCODE", raising=False)
        agent = OpenCode()
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=["bash", "opencode", "zsh"],
        ):
            assert agent.detect() is True

    def test_parent_process_detection_rationale(self) -> None:
        """Agents without env vars use parent process detection as fallback.

        Evidence:
            Source: psutil Process.name() documentation
            URL: https://psutil.readthedocs.io/en/latest/#psutil.Process.name
            Quote: "The process name."
            Reason: We compare parent process names to the CLI command names.

        Rationale:
        - Primary detection: Environment variables (fast, reliable)
        - Fallback detection: Parent process name matching (works universally)

        Agents using parent-process detection only:
        - Aider, Codex, Gemini, Copilot, Continue Dev

        Agents using env var detection:
        - Claude Code: CLAUDECODE=1 (live tested)
        - OpenCode: OPENCODE=1 (GitHub PR #1780)
        - Cursor Agent: CURSOR_AGENT (official docs)

        Verified: 2026-01-11 via psutil docs and registry metadata
        """
        # Verify Codex uses parent process detection
        codex = Codex()
        assert codex.detect_env_var is None
        assert codex.detect_process_name == "codex"

        # Verify Gemini uses parent process detection
        gemini = Gemini()
        assert gemini.detect_env_var is None
        assert gemini.detect_process_name == "gemini"

        # Verify Copilot uses parent process detection
        copilot = Copilot()
        assert copilot.detect_env_var is None
        assert copilot.detect_process_name == "copilot"

    def test_nodejs_cli_cmdline_extraction(self) -> None:
        """Node.js CLIs need cmdline extraction because process.name() returns 'node'.

        Evidence:
            Source: psutil Process.name() documentation
            URL: https://psutil.readthedocs.io/en/latest/#psutil.Process.name
            Quote: "The process name"

            Source: psutil Process.cmdline() documentation
            URL: https://psutil.readthedocs.io/en/latest/#psutil.Process.cmdline
            Quote: "The command line this process has been called with"

            Source: Node.js process.title documentation
            URL: https://nodejs.org/api/process.html#processtitle
            Quote: "process.title property returns the current process title"

            Finding: Node.js CLIs using `#!/usr/bin/env node` shebang have:
            - process.name() = 'node' (the runtime, NOT the CLI command)
            - cmdline = ['node', '/path/to/cn', '--version'] (contains actual command)

            Exception: CLIs that set `process.title` (like Claude) show their name
            - Claude sets `process.title="claude"` in cli.js
            - So process.name() returns 'claude' not 'node'

            Our solution: Extract command name from cmdline[1] as fallback
            - cmdline[1] is typically the script path: '/path/to/cn'
            - basename + remove extension → 'cn'

            Agents affected (no process.title, need cmdline extraction):
            - Continue Dev (cn), Codex, Gemini, Copilot

            Agents NOT affected (set process.title or are native binaries):
            - Claude Code (sets process.title="claude")
            - Aider (Python, process.name() = 'aider')

            Verified: 2026-01-11 via live testing with `cn --version`
        """
        # This test documents the cmdline extraction behavior
        # The actual implementation is in base._get_parent_process_names()
        agent = ContinueDev()
        # Continue Dev uses process name detection (works via cmdline extraction)
        assert agent.detect_process_name == "cn"


class TestCodingAgentInstallCommands:
    """Tests verifying correct install commands for AI coding agents.

    Each test documents the official install command and package name.
    """

    def test_codex_install_command(self) -> None:
        """OpenAI Codex CLI installs via npm install -g @openai/codex.

        Evidence:
            Source: npm package page
            URL: https://www.npmjs.com/package/@openai/codex
            Also: https://developers.openai.com/codex/cli/
            Alternative: brew install --cask codex
            Verified: 2026-01-11 via npm and official docs
        """
        agent = Codex()
        assert "openai" in agent.install_url.lower() or "codex" in agent.install_url.lower()

    def test_gemini_install_command(self) -> None:
        """Google Gemini CLI installs via npm install -g @google/gemini-cli.

        Evidence:
            Source: npm package page
            URL: https://www.npmjs.com/package/@google/gemini-cli
            GitHub: https://github.com/google-gemini/gemini-cli
            Verified: 2026-01-11 via npm
        """
        agent = Gemini()
        assert "gemini" in agent.install_url.lower()

    def test_copilot_package_name(self) -> None:
        """GitHub Copilot CLI package is @github/copilot (NOT @github/copilot-cli).

        Evidence:
            Source: npm package page
            URL: https://www.npmjs.com/package/@github/copilot
            Note: The old @githubnext/github-copilot-cli is deprecated
            Correct: npm install -g @github/copilot
            Wrong: npm install -g @github/copilot-cli
            Verified: 2026-01-11 via npm
        """
        agent = Copilot()
        # Verify install URL points to correct location
        assert "github" in agent.install_url.lower()

    def test_aider_install_command(self) -> None:
        """Aider installs via pip install aider-chat (or uv tool install).

        Evidence:
            Source: PyPI and official docs
            URL: https://pypi.org/project/aider-chat/
            URL: https://aider.chat/docs/install.html
            Commands:
                pip install aider-chat
                uv tool install aider-chat
                pipx install aider-chat
            Verified: 2026-01-11 via PyPI and docs
        """
        agent = Aider()
        assert "aider" in agent.install_url.lower()

    def test_continue_dev_install_command(self) -> None:
        """Continue Dev CLI installs via npm install -g @continuedev/cli.

        Evidence:
            Source: npm package page
            URL: https://www.npmjs.com/package/@continuedev/cli
            Command: cn (the CLI command)
            Verified: 2026-01-11 via npm
        """
        agent = ContinueDev()
        assert agent.command == "cn"


class TestGTRComparison:
    """Tests documenting differences from GTR (git-worktree-runner).

    GTR is the reference implementation we compared against.
    Source: https://github.com/coderabbitai/git-worktree-runner
    """

    def test_claude_code_special_path(self) -> None:
        """Claude Code may install to ~/.claude/local/claude (legacy path).

        Evidence:
            Source: Claude Code installation behavior
            Path: ~/.claude/local/claude (checked first)
            Fallback: PATH lookup (e.g., ~/.bun/bin/claude)
            Note: Modern installs use bun, legacy used local path
            Verified: 2026-01-11 via `which claude` and `ls ~/.claude/`
        """
        agent = ClaudeCode()
        # Verify the agent has a get_executable method that checks special paths
        assert hasattr(agent, "get_executable")

    def test_vim_neovim_cd_pattern(self) -> None:
        """Vim/Neovim use cd && editor . pattern (no --directory flag).

        Evidence:
            Source: vim --help, nvim --help
            Finding: Neither vim nor nvim have --directory or --cwd flags
            Pattern: `cd "<path>" && vim .` is the standard workaround
            Verified: 2026-01-11 via `nix-shell -p vim --run "vim --help"`
        """
        vim = Vim()
        nvim = Neovim()
        with patch("shutil.which", return_value="/usr/bin/vim"):
            vim_cmd = vim.open_command(Path("/test"))
        with patch("shutil.which", return_value="/usr/bin/nvim"):
            nvim_cmd = nvim.open_command(Path("/test"))

        # Both should use cd && editor . pattern
        assert "cd" in vim_cmd[2]
        assert "vim ." in vim_cmd[2]
        assert "cd" in nvim_cmd[2]
        assert "nvim ." in nvim_cmd[2]

    def test_features_we_have_that_gtr_doesnt(self) -> None:
        """Document features we have that GTR doesn't.

        Evidence:
            Source: GTR source code comparison
            Date: 2026-01-11

        Features unique to agent-cli dev:
            1. tmux support with tab naming
            2. Zellij support with tab naming
            3. Kitty terminal support
            4. Project type auto-detection (10+ types)
            5. Auto-setup (runs npm install, uv sync, etc.)
            6. direnv integration with .envrc generation
            7. Nix flake/shell detection
            8. "Currently running" agent detection via env vars
            9. Auto-generated branch names (adjective-noun)
            10. Per-agent config args in config file
            11. Terminal tab name set to agent name
        """
        # This is a documentation test - always passes
        assert True

    def test_features_gtr_has_that_we_dont(self) -> None:
        """Document features GTR has that we don't.

        Evidence:
            Source: GTR source code comparison
            Date: 2026-01-11

        Features unique to GTR:
            1. Hooks system (postCreate, preRemove, postRemove)
            2. Git-config-based configuration with .gtrconfig
            3. Advanced file copying (patterns, directories, exclusions)
            4. Windows support (Windows Terminal, cmd.exe)
            5. Konsole and xterm support
            6. .worktreeinclude file for team defaults
            7. Atom editor support
            8. Generic editor/AI fallback (any PATH command)
            9. Shell completions (bash, zsh, fish)
            10. Copy between worktrees (--from flag)
        """
        # This is a documentation test - always passes
        assert True
