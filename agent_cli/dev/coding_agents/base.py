"""Base class for AI coding agent adapters."""

from __future__ import annotations

import os
import shutil
from abc import ABC
from pathlib import PurePath
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
        # Check env var first (faster) - checks for "1" specifically
        if self.detect_env_var and os.environ.get(self.detect_env_var) == "1":
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

    def prompt_args(self, prompt: str) -> list[str]:
        """Return the CLI arguments to pass an initial prompt to the agent.

        Override this method in subclasses for agents that support initial prompts.
        Default implementation returns empty list (prompt not supported).

        Args:
            prompt: The initial prompt to pass to the agent

        Returns:
            List of CLI arguments (e.g., ["prompt text"] or ["-m", "prompt text"])

        """
        del prompt  # unused in base implementation
        return []

    def launch_command(
        self,
        path: Path,  # noqa: ARG002
        extra_args: list[str] | None = None,
        prompt: str | None = None,
    ) -> list[str]:
        """Return the command to launch this agent in a directory.

        Args:
            path: The directory to launch the agent in
            extra_args: Additional arguments to pass to the agent
            prompt: Optional initial prompt to pass to the agent

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
        if prompt:
            cmd.extend(self.prompt_args(prompt))
        return cmd

    def get_env(self) -> dict[str, str]:
        """Get any additional environment variables needed."""
        return {}

    def __repr__(self) -> str:  # noqa: D105
        status = "available" if self.is_available() else "not installed"
        return f"<{self.__class__.__name__} {self.name!r} ({status})>"


def _get_parent_process_names() -> list[str]:
    """Get names of parent processes (for detecting current agent).

    Extracts names from both process.name() and cmdline.
    This handles Node.js CLIs that don't set process.title:
    - process.name() returns 'node' for most Node.js CLI tools
    - cmdline contains the actual script path like '/path/to/cn'
    - CLI tools that set process.title (like Claude) show their name directly
    """
    try:
        import psutil  # noqa: PLC0415

        process = psutil.Process(os.getpid())
        names = []
        for _ in range(10):  # Limit depth
            process = process.parent()
            if process is None:
                break
            # Add the process name (works for native binaries and tools that set process.title)
            names.append(process.name().lower())

            # Also check cmdline for the actual command (handles Node.js/Python CLIs)
            # e.g., cmdline=['node', '/path/to/cn', '--version'] → extract 'cn'
            try:
                cmdline = process.cmdline()
                if len(cmdline) >= 2:  # noqa: PLR2004
                    # Get the script/command from cmdline[1] (the actual CLI tool)
                    cmd_name = PurePath(cmdline[1]).name.lower()
                    # Remove common extensions
                    for ext in (".js", ".py", ".sh", ".exe"):
                        if cmd_name.endswith(ext):
                            cmd_name = cmd_name[: -len(ext)]
                            break
                    if cmd_name and cmd_name not in names:
                        names.append(cmd_name)
            except (psutil.AccessDenied, psutil.ZombieProcess, IndexError):
                pass
        return names
    except ImportError:
        # psutil not available, return empty list
        return []
    except Exception:
        return []
