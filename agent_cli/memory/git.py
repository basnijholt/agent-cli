"""Git integration for memory versioning."""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("agent_cli.memory.git")


def _is_git_installed() -> bool:
    """Check if git is available in the path."""
    return shutil.which("git") is not None


def init_repo(path: Path) -> None:
    """Initialize a git repository if one does not exist."""
    if not _is_git_installed():
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
            encoding="utf-8",
            errors="replace",
        )
        # Configure local user if not set (to avoid commit errors)
        try:
            subprocess.run(
                ["git", "config", "user.email"],  # noqa: S607
                cwd=path,
                check=True,
                capture_output=True,
                encoding="utf-8",
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

        # Create .gitignore to exclude derived data (vector db, cache)
        gitignore_path = path / ".gitignore"
        if not gitignore_path.exists():
            gitignore_content = "chroma/\nmemory_index.json\n__pycache__/\n*.tmp\n.DS_Store\n"
            gitignore_path.write_text(gitignore_content, encoding="utf-8")

        # Create README.md
        readme_path = path / "README.md"
        if not readme_path.exists():
            readme_content = (
                "# Agent Memory Store\n\n"
                "This repository contains the long-term memory for the Agent CLI.\n"
                "Files are automatically managed and versioned by the memory server.\n\n"
                "- `entries/`: Markdown files containing facts and conversation logs.\n"
                "- `deleted/`: Soft-deleted memories (tombstones).\n"
            )
            readme_path.write_text(readme_content, encoding="utf-8")

        # Initial commit
        subprocess.run(["git", "add", "."], cwd=path, check=True)  # noqa: S607
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Initial commit"],  # noqa: S607
            cwd=path,
            check=False,
            capture_output=True,
            encoding="utf-8",
        )

    except subprocess.CalledProcessError:
        logger.exception("Failed to initialize git repo")


def commit_changes(path: Path, message: str) -> None:
    """Stage and commit all changes in the given path."""
    if not _is_git_installed():
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
            encoding="utf-8",
            errors="replace",
        )
        if not status.stdout.strip():
            return  # Nothing to commit

        logger.info("Committing changes to memory store: %s", message)
        subprocess.run(
            ["git", "add", "."],  # noqa: S607
            cwd=path,
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "commit", "-m", message],  # noqa: S607
            cwd=path,
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        logger.exception("Failed to commit changes")
