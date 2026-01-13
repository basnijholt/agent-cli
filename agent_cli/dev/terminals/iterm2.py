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

        def escape_applescript(s: str) -> str:
            """Escape string for AppleScript double-quoted string."""
            # Escape backslashes first, then double quotes
            return s.replace("\\", "\\\\").replace('"', '\\"')

        # Build the command to run in the new tab
        shell_cmd = f'cd "{path}" && {command}' if command else f'cd "{path}"'
        shell_cmd_escaped = escape_applescript(shell_cmd)

        # Build name setting if provided
        name_cmd = ""
        if tab_name:
            tab_name_escaped = escape_applescript(tab_name)
            name_cmd = f'\nset name to "{tab_name_escaped}"'

        # AppleScript to open new tab in iTerm2
        # Handle case where no window exists by creating one
        applescript = f"""
            tell application "iTerm2"
                if (count of windows) = 0 then
                    create window with default profile
                end if
                tell current window
                    create tab with default profile
                    tell current session{name_cmd}
                        write text "{shell_cmd_escaped}"
                    end tell
                end tell
            end tell
        """

        try:
            subprocess.run(
                ["osascript", "-e", applescript],  # noqa: S607
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False
