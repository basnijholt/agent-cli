"""GitHub Copilot CLI coding agent adapter."""

from __future__ import annotations

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
        # Copilot CLI does not set any detection env var, only parent process detection works
        parent_names = _get_parent_process_names()
        return any("copilot" in name for name in parent_names)

    def launch_command(
        self,
        path: Path,  # noqa: ARG002
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """Return the command to launch Copilot CLI."""
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed. Install from {self.install_url}"
            raise RuntimeError(msg)
        cmd = [exe]
        if extra_args:
            cmd.extend(extra_args)
        return cmd
