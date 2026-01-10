"""GitHub Copilot CLI coding agent adapter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base import CodingAgent, _get_parent_process_names

if TYPE_CHECKING:
    from pathlib import Path


class Copilot(CodingAgent):
    """GitHub Copilot CLI coding agent."""

    name = "copilot"
    command = "copilot"
    alt_commands = ()
    install_url = "https://github.com/github/copilot-cli"

    def detect(self) -> bool:
        """Detect if running inside Copilot CLI."""
        # Check environment variables
        if os.environ.get("COPILOT_SESSION"):
            return True

        # Check parent process names
        parent_names = _get_parent_process_names()
        return any("copilot" in name for name in parent_names)

    def launch_command(self, path: Path) -> list[str]:  # noqa: ARG002
        """Return the command to launch Copilot CLI."""
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed. Install from {self.install_url}"
            raise RuntimeError(msg)
        return [exe]
