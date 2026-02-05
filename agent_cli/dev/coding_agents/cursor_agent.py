"""Cursor Agent CLI coding agent adapter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base import CodingAgent

if TYPE_CHECKING:
    from pathlib import Path


class CursorAgent(CodingAgent):
    """Cursor Agent - AI agent mode for Cursor editor."""

    name = "cursor-agent"
    command = "cursor-agent"
    alt_commands = ("cursor",)
    install_url = "https://cursor.com"

    def detect(self) -> bool:
        """Detect if running inside Cursor Agent.

        CURSOR_AGENT uses presence check (not == "1"), so custom detection needed.
        """
        return os.environ.get("CURSOR_AGENT") is not None

    def launch_command(
        self,
        path: Path,  # noqa: ARG002
        extra_args: list[str] | None = None,
        prompt: str | None = None,
    ) -> list[str]:
        """Return the command to launch Cursor Agent."""
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed"
            if self.install_url:
                msg += f". Install from {self.install_url}"
            raise RuntimeError(msg)
        # Try cursor-agent first, fall back to cursor cli
        cmd = [exe] if exe.endswith("cursor-agent") else [exe, "cli"]
        if extra_args:
            cmd.extend(extra_args)
        if prompt:
            cmd.extend(self.prompt_args(prompt))
        return cmd
