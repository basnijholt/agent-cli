"""tmux terminal multiplexer adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

from .base import Terminal

if TYPE_CHECKING:
    from pathlib import Path


class Tmux(Terminal):
    """tmux - Terminal multiplexer."""

    name = "tmux"

    def detect(self) -> bool:
        """Detect if running inside tmux."""
        # Check TMUX environment variable
        return os.environ.get("TMUX") is not None

    def is_available(self) -> bool:
        """Check if tmux is available."""
        return shutil.which("tmux") is not None

    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
    ) -> bool:
        """Open a new window in tmux.

        Creates a new tmux window (similar to a tab) in the current session.
        """
        if not self.is_available():
            return False

        # Build the command to run in the new window
        shell_cmd = f'cd "{path}" && {command}' if command else None

        try:
            # Create new window in current session
            cmd = ["tmux", "new-window", "-c", str(path)]

            if tab_name:
                cmd.extend(["-n", tab_name])

            if shell_cmd:
                # Run command in new window
                cmd.extend([shell_cmd])

            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def open_new_pane(
        self,
        path: Path,
        command: str | None = None,
        *,
        horizontal: bool = False,
    ) -> bool:
        """Open a new pane in tmux (split current window).

        Args:
            path: Directory to open in
            command: Optional command to run
            horizontal: If True, split horizontally; otherwise vertically

        """
        if not self.is_available():
            return False

        try:
            split_flag = "-h" if horizontal else "-v"
            cmd = ["tmux", "split-window", split_flag, "-c", str(path)]

            if command:
                cmd.append(f'cd "{path}" && {command}')

            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False
