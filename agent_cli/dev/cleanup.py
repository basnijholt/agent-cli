"""Worktree cleanup operations."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from . import worktree

if TYPE_CHECKING:
    from pathlib import Path


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
) -> list[tuple[str, bool, str | None]]:
    """Remove a list of worktrees.

    Returns list of (branch_name, success, error_message) tuples.
    """
    results: list[tuple[str, bool, str | None]] = []
    for wt in worktrees_to_remove:
        success, error = worktree.remove_worktree(
            wt.path,
            force=force,
            delete_branch=True,
            repo_path=repo_root,
        )
        results.append((wt.branch or wt.path.name, success, error))
    return results
