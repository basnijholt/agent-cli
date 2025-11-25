"""Git integration for memory versioning."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path

LOGGER = logging.getLogger(__name__)


class GitCommandResult(NamedTuple):
    """Result of a git command execution."""

    returncode: int
    stdout: str
    stderr: str


def _is_git_installed() -> bool:
    """Check if git is available in the path."""
    return shutil.which("git") is not None


def _run_git_sync(
    args: list[str],
    cwd: Path,
    check: bool = True,
) -> GitCommandResult:
    """Run a git command synchronously."""
    proc = subprocess.run(
        ["git", *args],  # noqa: S607
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return GitCommandResult(proc.returncode, proc.stdout, proc.stderr)


async def _run_git_async(
    args: list[str],
    cwd: Path,
    check: bool = True,
) -> GitCommandResult:
    """Run a git command asynchronously."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    assert proc.returncode is not None
    stdout_text = stdout.decode("utf-8", errors="replace")
    stderr_text = stderr.decode("utf-8", errors="replace")

    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode,
            ["git", *args],
            output=stdout_text,
            stderr=stderr_text,
        )

    return GitCommandResult(proc.returncode, stdout_text, stderr_text)


def init_repo(path: Path) -> None:
    """Initialize a git repository if one does not exist."""
    if not _is_git_installed():
        LOGGER.warning("Git is not installed; skipping repository initialization.")
        return

    if (path / ".git").exists():
        return

    try:
        LOGGER.info("Initializing git repository in %s", path)
        _run_git_sync(["init"], cwd=path)

        # Configure local user if not set (to avoid commit errors)
        try:
            _run_git_sync(["config", "user.email"], cwd=path)
        except subprocess.CalledProcessError:
            # No email configured, set local config
            _run_git_sync(["config", "user.email", "agent-cli@local"], cwd=path)
            _run_git_sync(["config", "user.name", "Agent CLI"], cwd=path)

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
                "Files are automatically managed and versioned by the memory proxy.\n\n"
                "- `entries/`: Markdown files containing facts and conversation logs.\n"
                "- `deleted/`: Soft-deleted memories (tombstones).\n"
            )
            readme_path.write_text(readme_content, encoding="utf-8")

        # Initial commit
        _run_git_sync(["add", "."], cwd=path)
        _run_git_sync(
            ["commit", "--allow-empty", "-m", "Initial commit"],
            cwd=path,
            check=False,
        )

    except subprocess.CalledProcessError:
        LOGGER.exception("Failed to initialize git repo")


async def commit_changes(path: Path, message: str) -> None:
    """Stage and commit all changes in the given path."""
    if not _is_git_installed():
        return

    if not (path / ".git").exists():
        LOGGER.warning("Not a git repository: %s", path)
        return

    try:
        # Check if there are changes
        status = await _run_git_async(
            ["status", "--porcelain"],
            cwd=path,
            check=False,
        )
        if status.returncode != 0:
            LOGGER.error("Failed to check git status")
            return

        if not status.stdout.strip():
            return  # Nothing to commit

        LOGGER.info("Committing changes to memory store: %s", message)

        await _run_git_async(["add", "."], cwd=path)
        await _run_git_async(["commit", "-m", message], cwd=path)

    except Exception:
        LOGGER.exception("Failed to commit changes")
