"""tmux terminal multiplexer adapter."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .base import Terminal, TerminalHandle

if TYPE_CHECKING:
    from pathlib import Path

WORKTREE_OPTION = "@agent_cli_worktree"
WINDOW_LIST_FORMAT = "#{window_id}\t#{session_name}\t#{window_name}\t#{@agent_cli_worktree}"


@dataclass(frozen=True)
class TmuxWindow:
    """A tmux window discovered via cross-session inventory."""

    window_id: str
    session_name: str
    window_name: str


@dataclass(frozen=True)
class TmuxInventory:
    """Tagged tmux windows for a worktree, plus any lookup error."""

    windows: tuple[TmuxWindow, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class TmuxCleanupResult:
    """Result of killing tagged tmux windows for a worktree."""

    killed_windows: tuple[TmuxWindow, ...] = ()
    errors: tuple[str, ...] = ()


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
        """Build a deterministic tmux-safe session name for a repo."""
        repo_slug = re.sub(r"[^A-Za-z0-9_-]+", "-", repo_root.name).strip("-") or "repo"
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

    def current_window_id(self) -> str | None:
        """Get the tmux window id for the current pane, when available."""
        cmd = ["tmux", "display-message", "-p"]
        pane_id = os.environ.get("TMUX_PANE")
        if pane_id:
            cmd.extend(["-t", pane_id])
        cmd.append("#{window_id}")
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            if self._is_server_unavailable_error(e):
                return None
            return None
        window_id = result.stdout.strip()
        return window_id or None

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

        # Avoid a has-session/new-session race when several launches try to create the
        # same repo-scoped session concurrently: try new-window first, then create,
        # then retry new-window in case another launcher created the session first.
        handle = self._open_window(path, command, tab_name, session_name=session_name)
        if handle is not None:
            return handle

        handle = self._create_session(path, command, tab_name, session_name=session_name)
        if handle is not None:
            return handle

        return self._open_window(path, command, tab_name, session_name=session_name)

    def list_windows_for_worktree(self, worktree_path: Path) -> TmuxInventory:
        """List tagged tmux windows for a worktree across all sessions."""
        if not self.is_available():
            return TmuxInventory()

        normalized_path = self._normalize_worktree_path(worktree_path)
        try:
            result = subprocess.run(
                ["tmux", "list-windows", "-a", "-F", WINDOW_LIST_FORMAT],  # noqa: S607
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            if self._is_server_unavailable_error(e):
                return TmuxInventory()
            return TmuxInventory(
                error=f"Failed to inspect tmux windows for {normalized_path}: {self._error_text(e)}",
            )

        windows: list[TmuxWindow] = []
        for line in result.stdout.splitlines():
            if not line:
                continue
            parts = line.split("\t", maxsplit=3)
            if len(parts) != 4:  # noqa: PLR2004
                continue
            window_id, session_name, window_name, tagged_path = parts
            if tagged_path != normalized_path:
                continue
            windows.append(
                TmuxWindow(
                    window_id=window_id,
                    session_name=session_name,
                    window_name=window_name,
                ),
            )

        return TmuxInventory(windows=tuple(windows))

    def kill_windows_for_worktree(self, worktree_path: Path) -> TmuxCleanupResult:
        """Kill tagged tmux windows for a worktree across all sessions."""
        inventory = self.list_windows_for_worktree(worktree_path)
        if inventory.error is not None:
            return TmuxCleanupResult(errors=(inventory.error,))

        killed_windows: list[TmuxWindow] = []
        errors: list[str] = []
        current_window_id = self.current_window_id() if inventory.windows else None
        for window in inventory.windows:
            if current_window_id is not None and window.window_id == current_window_id:
                errors.append(
                    "Skipped tmux window "
                    f"{window.window_id} in session {window.session_name} "
                    "because it is the current window",
                )
                continue
            try:
                subprocess.run(
                    ["tmux", "kill-window", "-t", window.window_id],  # noqa: S607
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                errors.append(
                    "Failed to kill tmux window "
                    f"{window.window_id} in session {window.session_name}: {self._error_text(e)}",
                )
                continue
            killed_windows.append(window)

        return TmuxCleanupResult(
            killed_windows=tuple(killed_windows),
            errors=tuple(errors),
        )

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
        handle = self._spawn_target(
            ["tmux", "new-session", "-d", "-s", session_name],
            path=path,
            command=command,
            tab_name=tab_name,
            session_name=session_name,
        )
        if handle is None:
            return None
        subprocess.run(
            ["tmux", "set-option", "-t", session_name, "renumber-windows", "off"],  # noqa: S607
            capture_output=True,
            check=False,
        )
        return handle

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
        self._tag_window_for_worktree(pane_id, path)
        return TerminalHandle(
            terminal_name=self.name,
            handle=pane_id,
            session_name=session_name,
        )

    @staticmethod
    def _normalize_worktree_path(path: Path) -> str:
        """Normalize a worktree path for tmux window tagging and lookup."""
        return str(path.resolve(strict=False))

    @staticmethod
    def _error_text(exc: subprocess.CalledProcessError) -> str:
        """Extract a useful stderr/stdout payload from a tmux subprocess error."""
        stderr = exc.stderr.strip() if exc.stderr else ""
        stdout = exc.stdout.strip() if exc.stdout else ""
        return stderr or stdout or str(exc)

    @staticmethod
    def _is_server_unavailable_error(exc: subprocess.CalledProcessError) -> bool:
        """Detect tmux errors that mean there is no server/client to inspect."""
        stderr = exc.stderr.lower() if exc.stderr else ""
        return "no server running" in stderr or "no current client" in stderr

    def _tag_window_for_worktree(self, pane_id: str, worktree_path: Path) -> None:
        """Tag a tmux window with the owning worktree path for later cleanup."""
        tmux_executable = shutil.which("tmux")
        if tmux_executable is None:
            return

        subprocess.run(
            [
                tmux_executable,
                "set-option",
                "-w",
                "-t",
                pane_id,
                WORKTREE_OPTION,
                self._normalize_worktree_path(worktree_path),
            ],
            capture_output=True,
            check=False,
        )
