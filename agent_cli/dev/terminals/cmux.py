"""cmux terminal adapter.

cmux (https://cmux.dev) is a Ghostty-based macOS terminal organized as
windows > workspaces > panes > surfaces (tabs), controlled via a Unix
socket through the bundled ``cmux`` CLI.

agent-cli maps repos to workspaces: each repo gets a workspace named after
it, and each worktree launch opens a new tab inside that workspace.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from typing import TYPE_CHECKING

from agent_cli.dev.worktree import get_main_repo_root

from .base import Terminal, TerminalHandle

if TYPE_CHECKING:
    from pathlib import Path

# Named colors accepted by `cmux workspace-action --action set-color`.
_WORKSPACE_COLORS = (
    "Red",
    "Crimson",
    "Orange",
    "Amber",
    "Olive",
    "Green",
    "Teal",
    "Aqua",
    "Blue",
    "Navy",
    "Indigo",
    "Purple",
    "Magenta",
    "Rose",
    "Brown",
    "Charcoal",
)


class Cmux(Terminal):
    """cmux - Ghostty-based terminal with workspaces for AI coding agents."""

    name = "cmux"

    def detect(self) -> bool:
        """Detect if running inside cmux via its auto-set environment variables."""
        return bool(
            os.environ.get("CMUX_WORKSPACE_ID") or os.environ.get("CMUX_SURFACE_ID"),
        )

    def is_available(self) -> bool:
        """Check if the cmux CLI is available."""
        return shutil.which("cmux") is not None

    def open_new_tab(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
    ) -> bool:
        """Open a new tab in a workspace named after the repo containing ``path``."""
        repo_root = get_main_repo_root(path)
        workspace_name = (repo_root or path).name
        handle = self.open_in_workspace(path, command, tab_name, workspace_name=workspace_name)
        return handle is not None

    def open_in_workspace(
        self,
        path: Path,
        command: str | None = None,
        tab_name: str | None = None,
        *,
        workspace_name: str,
    ) -> TerminalHandle | None:
        """Open a tab in the named cmux workspace, creating the workspace if needed.

        Workspace targets are always passed explicitly because the cmux CLI
        otherwise defaults to the caller's workspace (``CMUX_WORKSPACE_ID``).
        """
        if not self.is_available():
            return None
        workspaces = self._list_workspaces()
        if workspaces is None:
            # The cmux CLI itself failed (e.g. app not running); creating a
            # workspace would fail too, or duplicate one we could not see.
            return None
        workspace_ref = next(
            (w.get("ref") for w in workspaces if w.get("title") == workspace_name),
            None,
        )
        if workspace_ref is None:
            return self._create_workspace(path, command, tab_name, workspace_name=workspace_name)
        return self._open_tab(
            path,
            command,
            tab_name,
            workspace_ref=workspace_ref,
            workspace_name=workspace_name,
        )

    def _list_workspaces(self) -> list[dict] | None:
        """List workspace dicts via the cmux CLI, or None when the CLI call fails."""
        stdout = self._run(["workspace", "list", "--json"])
        if stdout is None:
            return None
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return None
        workspaces = data.get("workspaces", [])
        return workspaces if isinstance(workspaces, list) else None

    def _create_workspace(
        self,
        path: Path,
        command: str | None,
        tab_name: str | None,
        *,
        workspace_name: str,
    ) -> TerminalHandle | None:
        """Create a workspace whose initial tab starts in ``path`` running ``command``."""
        cmd = ["workspace", "create", "--name", workspace_name, "--cwd", str(path)]
        if command:
            cmd.extend(["--command", command])
        workspace_ref = self._parse_ok_ref(self._run(cmd), "workspace:")
        if workspace_ref is None:
            return None
        self._run(
            [
                "workspace-action",
                "--action",
                "set-color",
                "--workspace",
                workspace_ref,
                "--color",
                self._workspace_color(workspace_name),
            ],
        )
        if tab_name:
            # The freshly created workspace has a single tab, which is its
            # focused tab, so rename-tab needs no explicit surface target.
            self._run(["rename-tab", "--workspace", workspace_ref, "--title", tab_name])
        return TerminalHandle(
            terminal_name=self.name,
            handle=workspace_ref,
            session_name=workspace_name,
        )

    def _open_tab(
        self,
        path: Path,
        command: str | None,
        tab_name: str | None,
        *,
        workspace_ref: str,
        workspace_name: str,
    ) -> TerminalHandle | None:
        """Open a new tab in an existing workspace and run ``command`` in ``path``."""
        surface_ref = self._parse_ok_ref(
            self._run(["new-surface", "--workspace", workspace_ref]),
            "surface:",
        )
        if surface_ref is None:
            return None
        if tab_name:
            self._run(
                [
                    "rename-tab",
                    "--workspace",
                    workspace_ref,
                    "--surface",
                    surface_ref,
                    "--title",
                    tab_name,
                ],
            )
        # New surfaces don't accept a cwd/command, so type it into the shell.
        # The terminal buffers the input until the shell is ready, and cmux
        # turns the literal \n escape sequence into Enter.
        shell_cmd = f"cd {shlex.quote(str(path))}"
        if command:
            shell_cmd += f" && {command}"
        sent = self._run(
            [
                "send",
                "--workspace",
                workspace_ref,
                "--surface",
                surface_ref,
                "--",
                shell_cmd + "\\n",
            ],
        )
        if sent is None:
            # The command never reached the tab, so the agent is not running;
            # remove the idle tab and report failure instead of a dead handle.
            self._run(["close-surface", "--workspace", workspace_ref, "--surface", surface_ref])
            return None
        return TerminalHandle(
            terminal_name=self.name,
            handle=surface_ref,
            session_name=workspace_name,
        )

    @staticmethod
    def _workspace_color(workspace_name: str) -> str:
        """Pick a deterministic cmux named color for a workspace."""
        digest = hashlib.sha256(workspace_name.encode()).hexdigest()
        return _WORKSPACE_COLORS[int(digest[:8], 16) % len(_WORKSPACE_COLORS)]

    @staticmethod
    def _run(args: list[str]) -> str | None:
        """Run a cmux CLI command and return its stdout, or None on failure."""
        env = {**os.environ, "CMUX_QUIET": "1"}
        try:
            result = subprocess.run(
                ["cmux", *args],  # noqa: S607
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
        except (subprocess.CalledProcessError, OSError):
            return None
        return result.stdout

    @staticmethod
    def _parse_ok_ref(stdout: str | None, prefix: str) -> str | None:
        """Extract the first ``<prefix>N`` ref from an ``OK ...`` response line."""
        if not stdout:
            return None
        for line in stdout.splitlines():
            if not line.startswith("OK"):
                continue
            for token in line.split():
                if token.startswith(prefix):
                    return token
        return None
