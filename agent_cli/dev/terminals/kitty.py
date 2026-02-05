"""Kitty terminal adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

from .base import Terminal

if TYPE_CHECKING:
    from pathlib import Path


class Kitty(Terminal):
    """Kitty - GPU-accelerated terminal emulator."""

    name = "kitty"

    def detect(self) -> bool:
        """Detect if running inside Kitty."""
        # Check KITTY_WINDOW_ID
        if os.environ.get("KITTY_WINDOW_ID"):
            return True
        # Check TERM
        term = os.environ.get("TERM", "")
        return "kitty" in term.lower()

    def is_available(self) -> bool:
        """Check if Kitty is available."""
        return shutil.which("kitty") is not None

    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
    ) -> bool:
        """Open a new tab in Kitty using kitten."""
        if not self.is_available():
            return False

        # Check if we're running inside Kitty
        if not self.detect():
            # Not in Kitty, open a new window instead
            cmd = ["kitty", "--directory", str(path)]
            if tab_name:
                cmd.extend(["--title", tab_name])
            if command:
                cmd.extend(["--", "sh", "-c", command])
            try:
                subprocess.Popen(cmd)
                return True
            except Exception:
                return False

        # Use kitten @ to control Kitty from inside
        cmd = [
            "kitten",
            "@",
            "launch",
            "--type=tab",
            f"--cwd={path}",
        ]

        if tab_name:
            cmd.append(f"--tab-title={tab_name}")

        if command:
            cmd.extend(["--", "sh", "-c", command])

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False
