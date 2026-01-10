"""OpenAI Codex CLI coding agent adapter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base import CodingAgent, _get_parent_process_names

if TYPE_CHECKING:
    from pathlib import Path


class Codex(CodingAgent):
    """OpenAI Codex CLI coding agent."""

    name = "codex"
    command = "codex"
    alt_commands = ()
    install_url = "https://github.com/openai/codex"

    def detect(self) -> bool:
        """Detect if running inside Codex."""
        # Check environment variables
        if os.environ.get("CODEX_SESSION"):
            return True

        # Check parent process names
        parent_names = _get_parent_process_names()
        return any("codex" in name for name in parent_names)

    def launch_command(self, path: Path) -> list[str]:  # noqa: ARG002
        """Return the command to launch Codex."""
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed. Install from {self.install_url}"
            raise RuntimeError(msg)
        return [exe]
