"""Low-level tmux operations for agent orchestration."""

from __future__ import annotations

import hashlib
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def open_window_with_pane_id(
    path: Path,
    command: str | None = None,
    tab_name: str | None = None,
) -> str | None:
    """Create a new tmux window and return the pane ID.

    Uses ``tmux new-window -P -F '#{pane_id}'`` to get the stable pane ID
    (e.g. ``%42``). Pane IDs are globally unique within a tmux server and
    remain stable when panes are moved or reordered.

    Returns the pane ID string, or ``None`` on failure.
    """
    cmd = ["tmux", "new-window", "-P", "-F", "#{pane_id}", "-c", str(path)]
    if tab_name:
        cmd.extend(["-n", tab_name])
    if command:
        cmd.append(command)
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        pane_id = result.stdout.strip()
        return pane_id or None
    except subprocess.CalledProcessError:
        return None


def capture_pane(pane_id: str, lines: int = 200) -> str | None:
    """Capture the last *lines* lines from a tmux pane.

    Returns the captured text, or ``None`` if the pane does not exist.
    """
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", f"-{lines}"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def send_keys(pane_id: str, text: str, *, enter: bool = True) -> bool:
    """Send text to a tmux pane.

    Returns ``True`` on success.
    """
    cmd = ["tmux", "send-keys", "-t", pane_id, text]
    if enter:
        cmd.append("Enter")
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def pane_exists(pane_id: str) -> bool:
    """Check if a tmux pane still exists."""
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{pane_id}"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        )
        return pane_id in result.stdout.splitlines()
    except subprocess.CalledProcessError:
        return False


def hash_output(text: str) -> str:
    """Compute a SHA-256 hash of text for quiescence detection."""
    return hashlib.sha256(text.encode()).hexdigest()
