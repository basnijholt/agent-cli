"""Base class for terminal adapters."""

from __future__ import annotations

import hashlib
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import subprocess
    from pathlib import Path


@dataclass(frozen=True)
class TerminalHandle:
    """Handle for a launched terminal target."""

    terminal_name: str
    handle: str
    session_name: str | None = None


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


class Multiplexer(Terminal):
    """Terminal multiplexer that can host named sessions with addressable tabs/windows."""

    def session_name_for_repo(self, repo_root: Path) -> str:
        """Build a deterministic session name for a repo (safe for tmux and zellij)."""
        repo_slug = re.sub(r"[^A-Za-z0-9_-]+", "-", repo_root.name).strip("-") or "repo"
        repo_hash = hashlib.sha256(str(repo_root).encode()).hexdigest()[:8]
        return f"agent-cli-{repo_slug[:24]}-{repo_hash}"

    @abstractmethod
    def current_session_name(self) -> str | None:
        """Get the session name this process is running inside, when available."""

    @abstractmethod
    def attach_command(self, session_name: str) -> str:
        """Shell command a user can run to attach to a session."""

    @abstractmethod
    def open_in_session(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
        *,
        session_name: str | None = None,
    ) -> TerminalHandle | None:
        """Open a tab/window and return its handle.

        If ``session_name`` is omitted, the current session is used.
        When a named session does not exist yet, it is created in detached mode.
        """


def subprocess_error_text(exc: subprocess.CalledProcessError) -> str:
    """Extract a useful stderr/stdout payload from a subprocess error."""
    stderr = exc.stderr.strip() if exc.stderr else ""
    stdout = exc.stdout.strip() if exc.stdout else ""
    return stderr or stdout or str(exc)


def _get_term_program() -> str | None:
    """Get the TERM_PROGRAM environment variable."""
    return os.environ.get("TERM_PROGRAM")
