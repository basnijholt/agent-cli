"""Claude Code AI coding agent adapter."""

from __future__ import annotations

import os
from pathlib import Path

from .base import CodingAgent, _get_parent_process_names


class ClaudeCode(CodingAgent):
    """Claude Code (Anthropic's CLI coding agent)."""

    name = "claude"
    command = "claude"
    alt_commands = ("claude-code",)
    install_url = "https://docs.anthropic.com/en/docs/claude-code"

    def detect(self) -> bool:
        """Detect if running inside Claude Code."""
        # Check environment variables
        if os.environ.get("CLAUDE_CODE"):
            return True

        # Check parent process names
        parent_names = _get_parent_process_names()
        return any("claude" in name for name in parent_names)

    def get_executable(self) -> str | None:
        """Get the Claude executable path."""
        # Check common installation path first
        local_claude = Path.home() / ".claude" / "local" / "claude"
        if local_claude.exists() and os.access(local_claude, os.X_OK):
            return str(local_claude)

        # Fall back to PATH lookup
        return super().get_executable()

    def launch_command(self, path: Path) -> list[str]:  # noqa: ARG002
        """Return the command to launch Claude Code."""
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed. Install from {self.install_url}"
            raise RuntimeError(msg)
        return [exe]
