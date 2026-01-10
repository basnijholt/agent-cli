"""Zellij terminal multiplexer adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

from .base import Terminal

if TYPE_CHECKING:
    from pathlib import Path


class Zellij(Terminal):
    """Zellij - A terminal workspace with batteries included."""

    name = "zellij"

    def detect(self) -> bool:
        """Detect if running inside Zellij."""
        # Check ZELLIJ environment variable
        return os.environ.get("ZELLIJ") is not None

    def is_available(self) -> bool:
        """Check if Zellij is available."""
        return shutil.which("zellij") is not None

    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
    ) -> bool:
        """Open a new tab in Zellij.

        Creates a new tab in the current Zellij session.
        """
        if not self.is_available():
            return False

        try:
            # Create new tab using zellij action
            subprocess.run(
                ["zellij", "action", "new-tab", "--cwd", str(path)],  # noqa: S607
                check=True,
                capture_output=True,
            )

            # If command specified, write it to the new pane
            if command:
                subprocess.run(
                    ["zellij", "action", "write-chars", f"cd {path} && {command}"],  # noqa: S607
                    check=True,
                    capture_output=True,
                )
                # Send enter key
                subprocess.run(
                    ["zellij", "action", "write", "10"],  # 10 is newline  # noqa: S607
                    check=True,
                    capture_output=True,
                )

            return True
        except subprocess.CalledProcessError:
            return False

    def open_new_pane(
        self,
        path: Path,
        command: str | None = None,
        *,
        direction: str = "down",
    ) -> bool:
        """Open a new pane in Zellij.

        Args:
            path: Directory to open in
            command: Optional command to run
            direction: Pane direction: "down", "up", "left", "right"

        """
        if not self.is_available():
            return False

        try:
            # Create new pane in specified direction
            subprocess.run(
                ["zellij", "action", "new-pane", "--direction", direction, "--cwd", str(path)],  # noqa: S607
                check=True,
                capture_output=True,
            )

            # If command specified, write it to the new pane
            if command:
                subprocess.run(
                    ["zellij", "action", "write-chars", f"cd {path} && {command}"],  # noqa: S607
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["zellij", "action", "write", "10"],  # noqa: S607
                    check=True,
                    capture_output=True,
                )

            return True
        except subprocess.CalledProcessError:
            return False
