"""Worktree cleanup operations."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import worktree
from .terminals.tmux import Tmux

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class RemoveWorktreeResult:
    """Outcome of removing a worktree and any tagged tmux windows."""

    name: str
    success: bool
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


def find_worktrees_with_no_commits(repo_root: Path) -> list[worktree.WorktreeInfo]:
    """Find worktrees whose branches have no commits ahead of the default branch."""
    worktrees_list = worktree.list_worktrees()
    default_branch = worktree.get_default_branch(repo_root)
    to_remove: list[worktree.WorktreeInfo] = []

    for wt in worktrees_list:
        if wt.is_main or not wt.branch:
            continue

        # Check if branch has any commits ahead of default branch
        result = subprocess.run(
            ["git", "rev-list", f"{default_branch}..{wt.branch}", "--count"],  # noqa: S607
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip() == "0":
            to_remove.append(wt)

    return to_remove


def find_worktrees_with_merged_prs(
    repo_root: Path,
) -> list[tuple[worktree.WorktreeInfo, str]]:
    """Find worktrees whose PRs have been merged on GitHub.

    Returns a list of tuples containing (worktree_info, pr_url).
    """
    worktrees_list = worktree.list_worktrees()
    to_remove: list[tuple[worktree.WorktreeInfo, str]] = []

    for wt in worktrees_list:
        if wt.is_main or not wt.branch:
            continue

        # Check if PR for this branch is merged
        result = subprocess.run(
            ["gh", "pr", "list", "--head", wt.branch, "--state", "merged", "--json", "number,url"],  # noqa: S607
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip() not in ("", "[]"):
            prs = json.loads(result.stdout)
            pr_url = prs[0]["url"] if prs else ""
            to_remove.append((wt, pr_url))

    return to_remove


def check_gh_available() -> tuple[bool, str]:
    """Check if GitHub CLI is available and authenticated.

    Returns (ok, error_message).
    """
    gh_version = subprocess.run(
        ["gh", "--version"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if gh_version.returncode != 0:
        return False, "GitHub CLI (gh) not found. Install from: https://cli.github.com/"

    gh_auth = subprocess.run(
        ["gh", "auth", "status"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if gh_auth.returncode != 0:
        return False, "Not authenticated with GitHub. Run: gh auth login"

    return True, ""


def remove_worktrees(
    worktrees_to_remove: list[worktree.WorktreeInfo],
    repo_root: Path,
    *,
    force: bool = False,
) -> list[RemoveWorktreeResult]:
    """Remove a list of worktrees.

    Returns a result for each worktree removal attempt.
    """
    return [
        remove_worktree(
            wt,
            repo_root,
            force=force,
            delete_branch=True,
        )
        for wt in worktrees_to_remove
    ]


def remove_worktree(
    wt: worktree.WorktreeInfo,
    repo_root: Path,
    *,
    force: bool = False,
    delete_branch: bool = False,
) -> RemoveWorktreeResult:
    """Remove one worktree and then clean up any tagged tmux windows."""
    removed, error = worktree.remove_worktree(
        wt.path,
        force=force,
        delete_branch=delete_branch,
        repo_path=repo_root,
    )
    result = RemoveWorktreeResult(
        name=wt.branch or wt.path.name,
        success=removed,
        error=error,
    )
    if not removed:
        return result

    tmux = Tmux()
    tmux_cleanup = tmux.kill_windows_for_worktree(wt.path)
    result.warnings.extend(tmux_cleanup.errors)
    return result
