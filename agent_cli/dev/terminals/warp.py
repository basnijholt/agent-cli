"""Warp terminal adapter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .base import Terminal, _get_term_program


class Warp(Terminal):
    """Warp - Modern, Rust-based terminal with AI features."""

    name = "warp"

    def detect(self) -> bool:
        """Detect if running inside Warp."""
        term_program = _get_term_program()
        return term_program is not None and "warp" in term_program.lower()

    def is_available(self) -> bool:
        """Check if Warp is available (macOS only for now)."""
        if sys.platform != "darwin":
            return False
        return Path("/Applications/Warp.app").exists()

    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
    ) -> bool:
        """Open a new tab in Warp using AppleScript."""
        if not self.is_available():
            return False

        # Build the command to run in the new tab
        shell_cmd = f'cd "{path}" && {command}' if command else f'cd "{path}"'

        # AppleScript to open new tab in Warp
        # Warp uses similar AppleScript interface to iTerm2
        applescript = f"""
            tell application "Warp"
                activate
                tell application "System Events"
                    tell process "Warp"
                        keystroke "t" using command down
                        delay 0.5
                        keystroke "{shell_cmd}"
                        keystroke return
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
