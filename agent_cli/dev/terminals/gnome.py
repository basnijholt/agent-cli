"""GNOME Terminal adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

from .base import Terminal

if TYPE_CHECKING:
    from pathlib import Path


class GnomeTerminal(Terminal):
    """GNOME Terminal - Default terminal for GNOME desktop."""

    name = "gnome-terminal"

    def detect(self) -> bool:
        """Detect if running inside GNOME Terminal."""
        return os.environ.get("GNOME_TERMINAL_SERVICE") is not None

    def is_available(self) -> bool:
        """Check if GNOME Terminal is available."""
        return shutil.which("gnome-terminal") is not None

    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
    ) -> bool:
        """Open a new tab in GNOME Terminal."""
        if not self.is_available():
            return False

        cmd = ["gnome-terminal", "--tab", f"--working-directory={path}"]

        if tab_name:
            cmd.extend(["--title", tab_name])

        if command:
            cmd.extend(["--", "bash", "-c", f"{command}; exec bash"])

        try:
            subprocess.Popen(cmd)
            return True
        except Exception:
            return False
