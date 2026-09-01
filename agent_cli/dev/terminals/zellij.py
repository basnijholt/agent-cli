"""Zellij terminal multiplexer adapter.

Multiplexer-style control (detached sessions, addressable tabs, cross-session
inventory) requires zellij >= 0.44.0, which returns stable tab IDs from
``new-tab``, accepts an initial command for new tabs, and supports
``list-panes --json`` / ``close-tab-by-id`` against detached sessions.
Older zellij versions fall back to the legacy in-session tab opening.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .base import Multiplexer, TerminalHandle, subprocess_error_text

# Minimum zellij version for CLI tab control (tab IDs, initial commands,
# list-panes --json, close-tab-by-id). See module docstring.
MIN_CONTROL_VERSION = (0, 44, 0)


@dataclass(frozen=True)
class ZellijTab:
    """A zellij tab discovered via cross-session inventory."""

    tab_id: int
    session_name: str
    tab_name: str


@dataclass(frozen=True)
class ZellijInventory:
    """Zellij tabs owned by a worktree, plus any lookup error."""

    tabs: tuple[ZellijTab, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class ZellijCleanupResult:
    """Result of closing zellij tabs for a worktree."""

    closed_tabs: tuple[ZellijTab, ...] = ()
    errors: tuple[str, ...] = ()


class Zellij(Multiplexer):
    """Zellij - A terminal workspace with batteries included."""

    name = "zellij"

    def detect(self) -> bool:
        """Detect if running inside Zellij."""
        # Check ZELLIJ environment variable
        return os.environ.get("ZELLIJ") is not None

    def is_available(self) -> bool:
        """Check if Zellij is available."""
        return shutil.which("zellij") is not None

    def current_session_name(self) -> str | None:
        """Get the current zellij session name."""
        return os.environ.get("ZELLIJ_SESSION_NAME") or None

    def attach_command(self, session_name: str) -> str:
        """Shell command a user can run to attach to a zellij session."""
        return f"zellij attach {shlex.quote(session_name)}"

    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
    ) -> bool:
        """Open a new tab in Zellij.

        Creates a new tab in the current Zellij session.
        """
        if not self.is_available():
            return False
        if self._supports_cli_control():
            return self.open_in_session(path, command, tab_name) is not None
        return self._open_new_tab_legacy(path, command, tab_name)

    def open_in_session(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
        *,
        session_name: str | None = None,
    ) -> TerminalHandle | None:
        """Open a zellij tab and return its handle.

        If ``session_name`` is omitted, the current zellij session is used.
        When a named session does not exist yet, it is created in detached mode.
        Requires zellij >= 0.44.0.
        """
        if not self.is_available() or not self._supports_cli_control():
            return None

        if session_name is None:
            if not self.detect():
                return None
            session_name = self.current_session_name()
            zellij_cmd = ["zellij"]
        else:
            if not self._ensure_session(session_name):
                return None
            zellij_cmd = ["zellij", "--session", session_name]

        cmd = [*zellij_cmd, "action", "new-tab", "--cwd", str(path)]
        if tab_name:
            cmd.extend(["--name", tab_name])
        if command:
            # The initial command is argv-style (no shell), so wrap it
            cmd.extend(["--", "/bin/sh", "-c", command])
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            return None
        return TerminalHandle(
            terminal_name=self.name,
            handle=result.stdout.strip(),
            session_name=session_name,
        )

    def list_tabs_for_worktree(self, worktree_path: Path) -> ZellijInventory:
        """List zellij tabs with a pane working in a worktree, across all live sessions."""
        if not self.is_available() or not self._supports_cli_control():
            return ZellijInventory()

        normalized_path = self._normalize_worktree_path(worktree_path)
        tabs: dict[tuple[str, int], ZellijTab] = {}
        errors: list[str] = []
        for session_name in self._live_session_names():
            panes, error = self._list_panes(session_name)
            if error is not None:
                errors.append(error)
                continue
            for pane in panes:
                tab_id = pane.get("tab_id")
                if (
                    pane.get("is_plugin")
                    or tab_id is None
                    or not self._pane_in_worktree(pane, normalized_path)
                ):
                    continue
                tabs.setdefault(
                    (session_name, tab_id),
                    ZellijTab(
                        tab_id=tab_id,
                        session_name=session_name,
                        tab_name=pane.get("tab_name") or "",
                    ),
                )

        return ZellijInventory(tabs=tuple(tabs.values()), error="; ".join(errors) or None)

    def close_tabs_for_worktree(self, worktree_path: Path) -> ZellijCleanupResult:
        """Close zellij tabs working in a worktree, across all live sessions."""
        inventory = self.list_tabs_for_worktree(worktree_path)
        errors: list[str] = [inventory.error] if inventory.error else []

        current_session = self.current_session_name()
        in_zellij = current_session is not None and os.environ.get("ZELLIJ_PANE_ID") is not None
        current_tab = self._current_tab() if inventory.tabs and in_zellij else None
        closed_tabs: list[ZellijTab] = []
        for tab in inventory.tabs:
            if current_tab == (tab.session_name, tab.tab_id):
                errors.append(
                    f"Skipped zellij tab {tab.tab_id} in session {tab.session_name} "
                    "because it is the current tab",
                )
                continue
            # Fail safe: if we are inside zellij but could not resolve our own tab,
            # never close tabs in the session we are running in.
            if in_zellij and current_tab is None and tab.session_name == current_session:
                errors.append(
                    f"Skipped zellij tab {tab.tab_id} in session {tab.session_name} "
                    "because the current tab could not be determined",
                )
                continue
            try:
                subprocess.run(
                    [  # noqa: S607
                        "zellij",
                        "--session",
                        tab.session_name,
                        "action",
                        "close-tab-by-id",
                        str(tab.tab_id),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as e:
                errors.append(
                    f"Failed to close zellij tab {tab.tab_id} in session "
                    f"{tab.session_name}: {subprocess_error_text(e)}",
                )
                continue
            closed_tabs.append(tab)

        return ZellijCleanupResult(closed_tabs=tuple(closed_tabs), errors=tuple(errors))

    def _open_new_tab_legacy(
        self,
        path: Path,
        command: str | None,
        tab_name: str | None,
    ) -> bool:
        """Open a tab on zellij < 0.44 by typing the command into the focused pane."""
        try:
            # Workaround: --cwd requires --layout on zellij < 0.43 (zellij-org/zellij#2981)
            cmd = ["zellij", "action", "new-tab", "--layout", "default", "--cwd", str(path)]
            if tab_name:
                cmd.extend(["--name", tab_name])
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )

            # If command specified, write it to the new pane
            # --cwd already sets the working directory, so no need for cd
            if command:
                # Small delay to ensure the new tab has focus
                time.sleep(0.1)
                subprocess.run(
                    ["zellij", "action", "write-chars", command],  # noqa: S607
                    check=True,
                    capture_output=True,
                    text=True,
                )
                # Send enter key
                subprocess.run(
                    ["zellij", "action", "write", "10"],  # 10 is newline  # noqa: S607
                    check=True,
                    capture_output=True,
                    text=True,
                )

            return True
        except subprocess.CalledProcessError:
            return False

    _supports_control: bool | None = None

    def _supports_cli_control(self) -> bool:
        """Whether the installed zellij supports tab IDs and detached-session control."""
        if self._supports_control is None:
            version = self._cli_version()
            self._supports_control = version is not None and version >= MIN_CONTROL_VERSION
        return self._supports_control

    @staticmethod
    def _cli_version() -> tuple[int, int, int] | None:
        """Parse the installed zellij version (e.g. "zellij 0.44.3")."""
        try:
            result = subprocess.run(
                ["zellij", "--version"],  # noqa: S607
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, OSError):
            return None
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout)
        if match is None:
            return None
        major, minor, patch = match.groups()
        return int(major), int(minor), int(patch)

    @staticmethod
    def _ensure_session(session_name: str) -> bool:
        """Create a detached session if it does not exist yet."""
        result = subprocess.run(
            ["zellij", "attach", "--create-background", session_name],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True
        # Non-interactive attach to an existing session fails with this message
        return "already exists" in f"{result.stdout}\n{result.stderr}".lower()

    @staticmethod
    def _live_session_names() -> list[str]:
        """List running (non-EXITED) zellij session names."""
        try:
            result = subprocess.run(
                ["zellij", "list-sessions", "--no-formatting"],  # noqa: S607
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, OSError):
            # zellij exits non-zero when there are no sessions at all
            return []
        names: list[str] = []
        for raw_line in result.stdout.splitlines():
            # Lines look like "<name> [Created ...]" with an optional
            # "(EXITED - attach to resurrect)" suffix; names may contain spaces.
            line = raw_line.strip()
            match = re.match(r"(.+?) \[Created ", line)
            if match is None or "(EXITED" in line[match.end() :]:
                continue
            names.append(match.group(1))
        return names

    @staticmethod
    def _list_panes(session_name: str) -> tuple[list[dict], str | None]:
        """List panes of a session as JSON dicts, with any lookup error."""
        try:
            result = subprocess.run(
                ["zellij", "--session", session_name, "action", "list-panes", "--json"],  # noqa: S607
                check=True,
                capture_output=True,
                text=True,
            )
            panes = json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            return [], (
                f"Failed to inspect zellij panes in session {session_name}: "
                f"{subprocess_error_text(e)}"
            )
        except json.JSONDecodeError as e:
            return [], f"Failed to parse zellij panes in session {session_name}: {e}"
        return panes, None

    @staticmethod
    def _pane_in_worktree(pane: dict, normalized_path: str) -> bool:
        """Whether a pane's working directory is inside a worktree."""
        pane_cwd = pane.get("pane_cwd")
        if not pane_cwd:
            return False
        try:
            return Path(pane_cwd).resolve(strict=False).is_relative_to(normalized_path)
        except (OSError, ValueError):
            return False

    @staticmethod
    def _normalize_worktree_path(path: Path) -> str:
        """Normalize a worktree path for pane cwd matching."""
        return str(path.resolve(strict=False))

    def _current_tab(self) -> tuple[str, int] | None:
        """Identify the (session, tab id) holding this process's pane, when inside zellij."""
        session_name = self.current_session_name()
        pane_id = os.environ.get("ZELLIJ_PANE_ID")
        if session_name is None or pane_id is None:
            return None
        panes, _error = self._list_panes(session_name)
        for pane in panes:
            if not pane.get("is_plugin") and str(pane.get("id")) == pane_id:
                tab_id = pane.get("tab_id")
                return (session_name, tab_id) if tab_id is not None else None
        return None
