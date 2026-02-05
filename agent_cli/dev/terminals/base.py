"""Base class for terminal adapters."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class Terminal(ABC):
    """Abstract base class for terminal adapters."""

    # Display name for the terminal
    name: str

    @abstractmethod
    def detect(self) -> bool:
        """Check if currently running inside this terminal.

        This is used to auto-detect which terminal to use.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this terminal is installed and available."""

    @abstractmethod
    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
    ) -> bool:
        """Open a new tab in this terminal.

        Args:
            path: The directory to open in
            command: Optional command to run in the new tab
            tab_name: Optional name for the new tab

        Returns:
            True if successful, False otherwise

        """

    def __repr__(self) -> str:  # noqa: D105
        status = "available" if self.is_available() else "not installed"
        return f"<{self.__class__.__name__} {self.name!r} ({status})>"


def _get_term_program() -> str | None:
    """Get the TERM_PROGRAM environment variable."""
    return os.environ.get("TERM_PROGRAM")
