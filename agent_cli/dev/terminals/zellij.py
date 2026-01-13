"""Zellij terminal multiplexer adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
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
        tab_name: str | None = None,
    ) -> bool:
        """Open a new tab in Zellij.

        Creates a new tab in the current Zellij session.
        """
        if not self.is_available():
            return False

        try:
            # Create new tab using zellij action
            # Workaround: --cwd requires --layout due to bug (github.com/zellij-org/zellij/issues/2981)
            cmd = ["zellij", "action", "new-tab", "--layout", "default", "--cwd", str(path)]
            if tab_name:
                cmd.extend(["--name", tab_name])
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )

            # If command specified, write it to the new pane
            # --cwd already sets the working directory, so no need for cd
            if command:
                # Small delay to ensure the new tab has focus
                time.sleep(0.1)
                subprocess.run(
                    ["zellij", "action", "write-chars", command],  # noqa: S607
                    check=True,
                    capture_output=True,
                    text=True,
                )
                # Send enter key
                subprocess.run(
                    ["zellij", "action", "write", "10"],  # 10 is newline  # noqa: S607
                    check=True,
                    capture_output=True,
                    text=True,
                )

            return True
        except subprocess.CalledProcessError:
            return False
