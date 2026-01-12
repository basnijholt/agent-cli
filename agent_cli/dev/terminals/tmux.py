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

        try:
            # Create new window in current session
            # -c sets the working directory, so no need for cd in command
            cmd = ["tmux", "new-window", "-c", str(path)]

            if tab_name:
                cmd.extend(["-n", tab_name])

            if command:
                # Run command in new window (cwd already set by -c)
                cmd.append(command)

            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False
