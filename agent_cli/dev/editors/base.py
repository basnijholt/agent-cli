"""Base class for editor adapters."""

from __future__ import annotations

import os
import shutil
from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class Editor(ABC):
    """Abstract base class for editor adapters."""

    # Display name for the editor
    name: str

    # CLI command to invoke the editor
    command: str

    # Alternative command names
    alt_commands: tuple[str, ...] = ()

    # URL for installation instructions
    install_url: str = ""

    # Declarative detection: env vars that indicate running inside this editor
    # e.g., ("NVIM", "NVIM_LISTEN_ADDRESS") for Neovim
    detect_env_vars: tuple[str, ...] = ()

    # Declarative detection: value to look for in TERM_PROGRAM
    # e.g., "vscode" will match if TERM_PROGRAM contains "vscode" (case-insensitive)
    detect_term_program: str | None = None

    def detect(self) -> bool:
        """Check if currently running inside this editor's terminal.

        Default implementation uses declarative detection attributes.
        Override for custom detection logic.
        """
        # Check env vars first
        for env_var in self.detect_env_vars:
            if os.environ.get(env_var):
                return True

        # Check TERM_PROGRAM
        if self.detect_term_program:
            term_program = os.environ.get("TERM_PROGRAM")
            if term_program and self.detect_term_program.lower() in term_program.lower():
                return True

        return False

    def is_available(self) -> bool:
        """Check if this editor is installed and available."""
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

    def open_command(self, path: Path) -> list[str]:
        """Return the command to open a directory in this editor.

        Args:
            path: The directory to open

        Returns:
            List of command arguments

        """
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed"
            raise RuntimeError(msg)
        return [exe, path.as_posix()]

    def __repr__(self) -> str:  # noqa: D105
        status = "available" if self.is_available() else "not installed"
        return f"<{self.__class__.__name__} {self.name!r} ({status})>"
