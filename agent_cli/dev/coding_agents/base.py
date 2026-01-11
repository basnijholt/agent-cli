"""Base class for AI coding agent adapters."""

from __future__ import annotations

import os
import shutil
from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class CodingAgent(ABC):
    """Abstract base class for AI coding agent adapters."""

    # Display name for the agent
    name: str

    # CLI command to invoke the agent
    command: str

    # Alternative command names (for detection)
    alt_commands: tuple[str, ...] = ()

    # URL for installation instructions
    install_url: str = ""

    # Declarative detection: env var that indicates running inside this agent
    # e.g., "CLAUDECODE" for Claude Code (checks if env var is set to "1")
    detect_env_var: str | None = None

    # Declarative detection: process name to look for in parent processes
    # e.g., "aider" will match any parent process containing "aider"
    detect_process_name: str | None = None

    def detect(self) -> bool:
        """Check if this agent is currently running/active in the environment.

        Default implementation uses declarative detection attributes.
        Override for custom detection logic.
        """
        # Check env var first (faster) - truthy check, not just "1"
        if self.detect_env_var and os.environ.get(self.detect_env_var):
            return True

        # Fall back to parent process detection
        if self.detect_process_name:
            parent_names = _get_parent_process_names()
            return any(self.detect_process_name in name for name in parent_names)

        return False

    def is_available(self) -> bool:
        """Check if this agent is installed and available."""
        if shutil.which(self.command):
            return True
        return any(shutil.which(cmd) for cmd in self.alt_commands)

    def get_executable(self) -> str | None:
        """Get the path to the executable."""
        if exe := shutil.which(self.command):
            return exe
        for cmd in self.alt_commands:
            if exe := shutil.which(cmd):
                return exe
        return None

    def launch_command(
        self,
        path: Path,  # noqa: ARG002
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """Return the command to launch this agent in a directory.

        Args:
            path: The directory to launch the agent in
            extra_args: Additional arguments to pass to the agent

        Returns:
            List of command arguments

        """
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed"
            if self.install_url:
                msg += f". Install from {self.install_url}"
            raise RuntimeError(msg)
        cmd = [exe]
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    def get_env(self) -> dict[str, str]:
        """Get any additional environment variables needed."""
        return {}

    def __repr__(self) -> str:  # noqa: D105
        status = "available" if self.is_available() else "not installed"
        return f"<{self.__class__.__name__} {self.name!r} ({status})>"


def _get_parent_process_names() -> list[str]:
    """Get names of parent processes (for detecting current agent)."""
    try:
        import psutil  # noqa: PLC0415

        process = psutil.Process(os.getpid())
        names = []
        for _ in range(10):  # Limit depth
            process = process.parent()
            if process is None:
                break
            names.append(process.name().lower())
        return names
    except ImportError:
        # psutil not available, return empty list
        return []
    except Exception:
        return []
