"""Base class for editor adapters."""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
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

    @abstractmethod
    def detect(self) -> bool:
        """Check if currently running inside this editor's terminal.

        This is used to auto-detect which editor to use.
        """

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
        return [exe, str(path)]

    def __repr__(self) -> str:  # noqa: D105
        status = "available" if self.is_available() else "not installed"
        return f"<{self.__class__.__name__} {self.name!r} ({status})>"


def _get_term_program() -> str | None:
    """Get the TERM_PROGRAM environment variable."""
    return os.environ.get("TERM_PROGRAM")
