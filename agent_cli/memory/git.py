"""Git integration for memory versioning."""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("agent_cli.memory.git")


def is_git_installed() -> bool:
    """Check if git is available in the path."""
    return shutil.which("git") is not None


def init_repo(path: Path) -> None:
    """Initialize a git repository if one does not exist."""
    if not is_git_installed():
        logger.warning("Git is not installed; skipping repository initialization.")
        return

    if (path / ".git").exists():
        return

    try:
        logger.info("Initializing git repository in %s", path)
        subprocess.run(
            ["git", "init"],  # noqa: S607
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
        )
        # Configure local user if not set (to avoid commit errors)
        try:
            subprocess.run(
                ["git", "config", "user.email"],  # noqa: S607
                cwd=path,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            # No email configured, set local config
            subprocess.run(
                ["git", "config", "user.email", "agent-cli@local"],  # noqa: S607
                cwd=path,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Agent CLI"],  # noqa: S607
                cwd=path,
                check=True,
            )

        # Initial commit
        subprocess.run(["git", "add", "."], cwd=path, check=True)  # noqa: S607
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Initial commit"],  # noqa: S607
            cwd=path,
            check=False,
            capture_output=True,
        )

    except subprocess.CalledProcessError:
        logger.exception("Failed to initialize git repo")


def commit_changes(path: Path, message: str) -> None:
    """Stage and commit all changes in the given path."""
    if not is_git_installed():
        return

    if not (path / ".git").exists():
        logger.warning("Not a git repository: %s", path)
        return

    try:
        # Check if there are changes
        status = subprocess.run(
            ["git", "status", "--porcelain"],  # noqa: S607
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        if not status.stdout.strip():
            return  # Nothing to commit

        logger.info("Committing changes to memory store: %s", message)
        subprocess.run(
            ["git", "add", "."],  # noqa: S607
            cwd=path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message],  # noqa: S607
            cwd=path,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        logger.exception("Failed to commit changes")
