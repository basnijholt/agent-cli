"""iTerm2 terminal adapter."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .base import Terminal, _get_term_program


class ITerm2(Terminal):
    """iTerm2 - macOS terminal emulator with advanced features."""

    name = "iterm2"

    def detect(self) -> bool:
        """Detect if running inside iTerm2."""
        # Check TERM_PROGRAM
        term_program = _get_term_program()
        if term_program and "iterm" in term_program.lower():
            return True
        # Check iTerm-specific env var
        return os.environ.get("ITERM_SESSION_ID") is not None

    def is_available(self) -> bool:
        """Check if iTerm2 is available (macOS only)."""
        if sys.platform != "darwin":
            return False
        # Check if iTerm2 app exists
        return Path("/Applications/iTerm.app").exists()

    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
    ) -> bool:
        """Open a new tab in iTerm2 using AppleScript."""
        if not self.is_available():
            return False

        # Build the command to run in the new tab
        shell_cmd = f'cd "{path}" && {command}' if command else f'cd "{path}"'

        # Build name setting if provided
        name_cmd = f'\nset name to "{tab_name}"' if tab_name else ""

        # AppleScript to open new tab in iTerm2
        applescript = f"""
            tell application "iTerm2"
                tell current window
                    create tab with default profile
                    tell current session{name_cmd}
                        write text "{shell_cmd}"
                    end tell
                end tell
            end tell
        """

        try:
            subprocess.run(
                ["osascript", "-e", applescript],  # noqa: S607
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False
