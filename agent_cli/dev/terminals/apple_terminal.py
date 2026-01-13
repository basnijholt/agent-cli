"""macOS Terminal.app adapter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .base import Terminal, _get_term_program


class AppleTerminal(Terminal):
    """macOS Terminal.app - the default macOS terminal."""

    name = "terminal"

    def detect(self) -> bool:
        """Detect if running inside Terminal.app."""
        term_program = _get_term_program()
        return term_program == "Apple_Terminal"

    def is_available(self) -> bool:
        """Check if Terminal.app is available (macOS only)."""
        if sys.platform != "darwin":
            return False
        # Terminal.app is always available on macOS
        return Path("/System/Applications/Utilities/Terminal.app").exists()

    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
    ) -> bool:
        """Open a new tab in Terminal.app using AppleScript.

        Requires System Events accessibility permissions in
        System Preferences > Privacy & Security > Accessibility.
        """
        if not self.is_available():
            return False

        def escape_applescript(s: str) -> str:
            """Escape string for AppleScript double-quoted string."""
            return s.replace("\\", "\\\\").replace('"', '\\"')

        # Build the command to run
        shell_cmd = f'cd "{path}" && {command}' if command else f'cd "{path}"'
        shell_cmd_escaped = escape_applescript(shell_cmd)

        # Build custom title command if provided
        title_cmd = ""
        if tab_name:
            tab_name_escaped = escape_applescript(tab_name)
            title_cmd = (
                f'\nset custom title of selected tab of front window to "{tab_name_escaped}"'
            )

        # AppleScript to open new tab in Terminal.app using System Events
        applescript = f"""
            tell application "Terminal"
                activate
            end tell
            tell application "System Events"
                keystroke "t" using command down
            end tell
            delay 0.3
            tell application "Terminal"
                do script "{shell_cmd_escaped}" in selected tab of front window{title_cmd}
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
