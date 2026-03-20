"""tmux terminal multiplexer adapter."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

from .base import Terminal, TerminalHandle

if TYPE_CHECKING:
    from pathlib import Path


class Tmux(Terminal):
    """tmux - Terminal multiplexer."""

    name = "tmux"

    def detect(self) -> bool:
        """Detect if running inside tmux."""
        # Check TMUX environment variable
        return os.environ.get("TMUX") is not None

    def is_available(self) -> bool:
        """Check if tmux is available."""
        return shutil.which("tmux") is not None

    def session_name_for_repo(self, repo_root: Path) -> str:
        """Build a deterministic tmux session name for a repo."""
        repo_slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", repo_root.name).strip("-") or "repo"
        repo_hash = hashlib.sha256(str(repo_root).encode()).hexdigest()[:8]
        return f"agent-cli-{repo_slug[:24]}-{repo_hash}"

    def current_session_name(self) -> str | None:
        """Get the current tmux session name."""
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{session_name}"],  # noqa: S607
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError:
            return None
        session_name = result.stdout.strip()
        return session_name or None

    def session_exists(self, session_name: str) -> bool:
        """Check if a tmux session exists."""
        try:
            subprocess.run(
                ["tmux", "has-session", "-t", session_name],  # noqa: S607
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def open_in_session(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
        *,
        session_name: str | None = None,
    ) -> TerminalHandle | None:
        """Open a tmux window and return its pane handle.

        If ``session_name`` is omitted, the current tmux session is used.
        When a named session does not exist yet, it is created in detached mode.
        """
        if not self.is_available():
            return None

        if session_name is None:
            session_name = self.current_session_name()
            if session_name is None:
                return None
            return self._open_window(path, command, tab_name, session_name=session_name)

        if self.session_exists(session_name):
            return self._open_window(path, command, tab_name, session_name=session_name)
        return self._create_session(path, command, tab_name, session_name=session_name)

    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
    ) -> bool:
        """Open a new window in tmux.

        Creates a new tmux window (similar to a tab) in the current session.
        """
        return self.open_in_session(path, command, tab_name) is not None

    def _open_window(
        self,
        path: Path,
        command: str | None,
        tab_name: str | None,
        *,
        session_name: str,
    ) -> TerminalHandle | None:
        """Open a new window in an existing tmux session."""
        return self._spawn_target(
            ["tmux", "new-window", "-t", session_name],
            path=path,
            command=command,
            tab_name=tab_name,
            session_name=session_name,
        )

    def _create_session(
        self,
        path: Path,
        command: str | None,
        tab_name: str | None,
        *,
        session_name: str,
    ) -> TerminalHandle | None:
        """Create a detached tmux session and return its initial pane handle."""
        return self._spawn_target(
            ["tmux", "new-session", "-d", "-s", session_name],
            path=path,
            command=command,
            tab_name=tab_name,
            session_name=session_name,
        )

    def _spawn_target(
        self,
        base_cmd: list[str],
        *,
        path: Path,
        command: str | None,
        tab_name: str | None,
        session_name: str,
    ) -> TerminalHandle | None:
        """Run a tmux new-window/new-session command and capture its pane handle."""
        cmd = [*base_cmd, "-P", "-F", "#{pane_id}", "-c", str(path)]
        if tab_name:
            cmd.extend(["-n", tab_name])
        if command:
            cmd.append(command)
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            return None
        pane_id = result.stdout.strip()
        if not pane_id:
            return None
        return TerminalHandle(
            terminal_name=self.name,
            handle=pane_id,
            session_name=session_name,
        )
