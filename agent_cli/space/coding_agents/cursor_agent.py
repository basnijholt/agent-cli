"""Cursor Agent CLI coding agent adapter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base import CodingAgent, _get_parent_process_names

if TYPE_CHECKING:
    from pathlib import Path


class CursorAgent(CodingAgent):
    """Cursor Agent - AI agent mode for Cursor editor."""

    name = "cursor-agent"
    command = "cursor-agent"
    alt_commands = ("cursor",)
    install_url = "https://cursor.com"

    def detect(self) -> bool:
        """Detect if running inside Cursor Agent."""
        # Check environment variables
        if os.environ.get("CURSOR_AGENT_SESSION"):
            return True

        # Check parent process names
        parent_names = _get_parent_process_names()
        return any("cursor-agent" in name for name in parent_names)

    def launch_command(self, path: Path) -> list[str]:  # noqa: ARG002
        """Return the command to launch Cursor Agent."""
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed. Install from {self.install_url}"
            raise RuntimeError(msg)
        # Try cursor-agent first, fall back to cursor cli
        if exe.endswith("cursor-agent"):
            return [exe]
        return [exe, "cli"]
