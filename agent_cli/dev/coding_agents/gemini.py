"""Google Gemini CLI coding agent adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import CodingAgent, _get_parent_process_names

if TYPE_CHECKING:
    from pathlib import Path


class Gemini(CodingAgent):
    """Google Gemini CLI coding agent."""

    name = "gemini"
    command = "gemini"
    alt_commands = ()
    install_url = "https://github.com/google-gemini/gemini-cli"

    def detect(self) -> bool:
        """Detect if running inside Gemini CLI."""
        # Gemini CLI does not set any detection env var, only parent process detection works
        parent_names = _get_parent_process_names()
        return any("gemini" in name for name in parent_names)

    def launch_command(
        self,
        path: Path,  # noqa: ARG002
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """Return the command to launch Gemini."""
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed. Install from {self.install_url}"
            raise RuntimeError(msg)
        cmd = [exe]
        if extra_args:
            cmd.extend(extra_args)
        return cmd
