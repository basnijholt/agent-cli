"""Base class for AI coding agent adapters."""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
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

    @abstractmethod
    def detect(self) -> bool:
        """Check if this agent is currently running/active in the environment.

        This is used to auto-detect which agent to use when creating a new space.
        """

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

    def launch_command(self, path: Path) -> list[str]:  # noqa: ARG002
        """Return the command to launch this agent in a directory.

        Args:
            path: The directory to launch the agent in

        Returns:
            List of command arguments

        """
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed"
            raise RuntimeError(msg)
        return [exe]

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
