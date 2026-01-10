"""Continue Dev CLI coding agent adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import CodingAgent, _get_parent_process_names

if TYPE_CHECKING:
    from pathlib import Path


class ContinueDev(CodingAgent):
    """Continue Dev - AI code assistant."""

    name = "continue"
    command = "cn"
    alt_commands = ("continue",)
    install_url = "https://continue.dev"

    def detect(self) -> bool:
        """Detect if running inside Continue Dev."""
        # Continue Dev does not set any detection env var, only parent process detection works
        parent_names = _get_parent_process_names()
        return any("continue" in name or name == "cn" for name in parent_names)

    def launch_command(
        self,
        path: Path,  # noqa: ARG002
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """Return the command to launch Continue Dev."""
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed. Install from {self.install_url}"
            raise RuntimeError(msg)
        cmd = [exe]
        if extra_args:
            cmd.extend(extra_args)
        return cmd
