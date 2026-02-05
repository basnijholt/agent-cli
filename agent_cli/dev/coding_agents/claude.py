"""Claude Code AI coding agent adapter."""

from __future__ import annotations

import os
from pathlib import Path

from .base import CodingAgent


class ClaudeCode(CodingAgent):
    """Claude Code (Anthropic's CLI coding agent)."""

    name = "claude"
    command = "claude"
    alt_commands = ("claude-code",)
    install_url = "https://code.claude.com/docs/en/overview"
    detect_env_var = "CLAUDECODE"
    detect_process_name = "claude"

    def prompt_args(self, prompt: str) -> list[str]:
        """Return prompt as positional argument.

        Claude Code accepts prompt as a positional argument:
        `claude "your prompt here"`

        See: claude --help
        """
        return [prompt]

    def get_executable(self) -> str | None:
        """Get the Claude executable path."""
        # Check common installation path first
        local_claude = Path.home() / ".claude" / "local" / "claude"
        if local_claude.exists() and os.access(local_claude, os.X_OK):
            return str(local_claude)

        # Fall back to PATH lookup
        return super().get_executable()
