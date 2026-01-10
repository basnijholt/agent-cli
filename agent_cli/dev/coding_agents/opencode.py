"""OpenCode CLI coding agent adapter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base import CodingAgent, _get_parent_process_names

if TYPE_CHECKING:
    from pathlib import Path


class OpenCode(CodingAgent):
    """OpenCode - AI coding assistant."""

    name = "opencode"
    command = "opencode"
    alt_commands = ()
    install_url = "https://opencode.ai"

    def detect(self) -> bool:
        """Detect if running inside OpenCode."""
        # Check OPENCODE environment variable (set by OpenCode since PR #1780)
        if os.environ.get("OPENCODE") == "1":
            return True

        # Check parent process names
        parent_names = _get_parent_process_names()
        return any("opencode" in name for name in parent_names)

    def launch_command(self, path: Path) -> list[str]:  # noqa: ARG002
        """Return the command to launch OpenCode."""
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed. Install from {self.install_url}"
            raise RuntimeError(msg)
        return [exe]
