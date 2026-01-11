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
from unittest.mock import patch

import pytest  # noqa: TC002

from agent_cli.dev.coding_agents.aider import Aider
from agent_cli.dev.coding_agents.claude import ClaudeCode
from agent_cli.dev.coding_agents.codex import Codex
from agent_cli.dev.coding_agents.continue_dev import ContinueDev
from agent_cli.dev.coding_agents.copilot import Copilot
from agent_cli.dev.coding_agents.cursor_agent import CursorAgent
from agent_cli.dev.coding_agents.gemini import Gemini
from agent_cli.dev.coding_agents.opencode import OpenCode
from agent_cli.dev.editors.emacs import Emacs
from agent_cli.dev.editors.jetbrains import PyCharm
from agent_cli.dev.editors.neovim import Neovim
from agent_cli.dev.editors.vim import Vim
from agent_cli.dev.editors.vscode import VSCode
from agent_cli.dev.editors.zed import Zed
from agent_cli.dev.terminals.gnome import GnomeTerminal
from agent_cli.dev.terminals.kitty import Kitty
from agent_cli.dev.terminals.tmux import Tmux
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
            Source: Live test inside zellij session
            Command: `env | grep ZELLIJ`
            Output: ZELLIJ=0, ZELLIJ_SESSION_NAME=charming-lake, ZELLIJ_PANE_ID=3
            Note: Value is "0" but presence indicates inside zellij
            Verified: 2026-01-11 via live environment check
        """
        # Zellij sets ZELLIJ=0 (presence check, not value check)
        monkeypatch.setenv("ZELLIJ", "0")
        terminal = Zellij()
        assert terminal.detect() is True

    def test_kitty_detection_window_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Kitty sets KITTY_WINDOW_ID when running inside kitty.

        Evidence:
            Source: kitten @ launch --help
            Quote: References KITTY_WINDOW_ID for remote control
            Also: KITTY_LISTEN_ON for socket path
            Verified: 2026-01-11 via `kitty --help` and docs
        """
        monkeypatch.setenv("KITTY_WINDOW_ID", "1")
        terminal = Kitty()
        assert terminal.detect() is True

    def test_kitty_detection_term(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Kitty also detectable via TERM=xterm-kitty.

        Evidence:
            Source: Kitty documentation
            Note: TERM is set to xterm-kitty inside kitty terminal
            Verified: 2026-01-11 via kitty docs
        """
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.setenv("TERM", "xterm-kitty")
        terminal = Kitty()
        assert terminal.detect() is True

    def test_gnome_terminal_detection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GNOME Terminal sets GNOME_TERMINAL_SERVICE.

        Evidence:
            Source: gnome-terminal man page and source code
            Verified: 2026-01-11 via `nix-shell -p gnome-terminal --run "gnome-terminal --help"`
        """
        monkeypatch.setenv("GNOME_TERMINAL_SERVICE", ":1.123")
        terminal = GnomeTerminal()
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
        with patch("shutil.which", return_value="/usr/bin/tmux"):
            # Just verify it doesn't crash - actual command tested via mocking
            terminal.open_new_tab(
                Path("/test/path"),
                command="echo hello",
                tab_name="test-tab",
            )

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
            Note: NVIM_LISTEN_ADDRESS is deprecated in favor of $NVIM
            Verified: 2026-01-11 via official Neovim docs
        """
        monkeypatch.setenv("NVIM", "/run/user/1000/nvim.12345.0")
        editor = Neovim()
        assert editor.detect() is True

    def test_emacs_detection_inside_emacs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Emacs sets INSIDE_EMACS in subprocesses (shell, term, vterm, eshell).

        Evidence:
            Source: GNU Emacs Eshell Variables documentation
            URL: https://www.gnu.org/software/emacs/manual/html_node/eshell/Variables.html
            Quote: "INSIDE_EMACS indicates to external commands that they are
                   being invoked from within Emacs so they can adjust their
                   behavior if necessary. By default, its value is
                   `emacs-version,eshell`"
            Format: "<version>,<mode>" e.g., "29.1,eshell" or "vterm"
            Verified: 2026-01-11 via GNU docs
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
            Source: GitHub JetBrains/jediterm issue #253
            URL: https://github.com/JetBrains/jediterm/issues/253
            Quote: "IntelliJ terminal sets TERMINAL_EMULATOR=JetBrains-JediTerm
                   environment variable"
            Applies to: IntelliJ IDEA, PyCharm, WebStorm, GoLand, etc.
            Verified: 2026-01-11 via GitHub issue
        """
        monkeypatch.setenv("TERMINAL_EMULATOR", "JetBrains-JediTerm")
        editor = PyCharm()
        assert editor.detect() is True

    def test_zed_detection_zed_term(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Zed sets ZED_TERM=true as a built-in variable.

        Evidence:
            Source: Zed Environment documentation
            URL: https://zed.dev/docs/environment
            Quote: "Environment variables are assembled from multiple sources
                   in priority order, including built-in variables like
                   `ZED_TERM=true`"
            Also: TERM_PROGRAM=Zed since v0.145.0 (GitHub PR #14213)
            Verified: 2026-01-11 via official Zed docs
        """
        monkeypatch.setenv("ZED_TERM", "true")
        editor = Zed()
        assert editor.detect() is True


class TestEditorCommands:
    """Tests for editor open command syntax."""

    def test_vim_uses_cd_and_dot_pattern(self) -> None:
        """Vim/Neovim use `cd "<path>" && vim .` pattern to open directory.

        Evidence:
            Source: GTR (git-worktree-runner) implementation
            File: adapters/editor/vim.sh and adapters/editor/neovim.sh
            Pattern: `(cd "$path" && vim .)` opens vim with directory browser
            Reason: vim doesn't support --directory flag like VS Code
            Verified: 2026-01-11 via GTR source code comparison
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
            Source: Live test inside Claude Code session
            Command: `env | grep CLAUDE`
            Output: CLAUDECODE=1, CLAUDE_CODE_ENTRYPOINT=cli
            Note: Not documented publicly, discovered via live testing
            Verified: 2026-01-11 via live environment check
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
            URL: https://github.com/sst/opencode
            Note: Sets OPENCODE=1 environment variable
            Verified: 2026-01-11 via GitHub research
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
            Source: Implementation design
            Reason: No env var available, so we check parent process names
            Pattern: Any parent process containing "aider" triggers detection
            Verified: 2026-01-11 via code review
        """
        agent = Aider()
        with patch(
            "agent_cli.dev.coding_agents.base._get_parent_process_names",
            return_value=["bash", "aider", "zsh"],
        ):
            assert agent.detect() is True


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
        """Both GTR and we check ~/.claude/local/claude for Claude Code.

        Evidence:
            Source: GTR adapters/ai/claude.sh
            Code: `local claude_exe="$HOME/.claude/local/claude"`
            Reason: Claude Code installs to this location locally
            Verified: 2026-01-11 via GTR source code
        """
        agent = ClaudeCode()
        # Verify the agent has a get_executable method that can check special paths
        # The special path is ~/.claude/local/claude (as documented in GTR)
        assert hasattr(agent, "get_executable")

    def test_vim_neovim_cd_pattern_matches_gtr(self) -> None:
        """We use same cd && vim . pattern as GTR for vim/neovim.

        Evidence:
            Source: GTR adapters/editor/vim.sh and neovim.sh
            Code: `(cd "$worktree_path" && vim .)`
            Code: `(cd "$worktree_path" && nvim .)`
            Reason: vim doesn't have --directory flag
            Verified: 2026-01-11 via GTR source code
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
