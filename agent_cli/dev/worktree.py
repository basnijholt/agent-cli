"""Git worktree operations for the dev module."""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def _run_git(
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
    capture_output: bool = True,
    allow_file_protocol: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    cmd = ["git"]
    # Allow file:// protocol for local clones (disabled by default in newer git)
    if allow_file_protocol:
        cmd.extend(["-c", "protocol.file.allow=always"])
    cmd.extend(args)
    # Suppress SSH "Permanently added host" warnings by setting LogLevel=ERROR
    env = os.environ.copy()
    env.setdefault("GIT_SSH_COMMAND", "ssh -o LogLevel=ERROR")
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        capture_output=capture_output,
        text=True,
        env=env,
    )


def git_available() -> bool:
    """Check if git is available."""
    return shutil.which("git") is not None


def is_git_repo(path: Path | None = None) -> bool:
    """Check if the given path is inside a git repository."""
    try:
        result = _run_git("rev-parse", "--git-dir", cwd=path, check=False)
        return result.returncode == 0
    except Exception:
        return False


def has_origin_remote(path: Path | None = None) -> bool:
    """Check if the repository has an 'origin' remote configured."""
    try:
        result = _run_git("remote", "get-url", "origin", cwd=path, check=False)
        return result.returncode == 0
    except Exception:
        return False


def get_repo_root(path: Path | None = None) -> Path | None:
    """Get the root directory of the git repository."""
    try:
        result = _run_git("rev-parse", "--show-toplevel", cwd=path)
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def get_common_dir(path: Path | None = None) -> Path | None:
    """Get the common git directory (shared across worktrees)."""
    try:
        result = _run_git("rev-parse", "--git-common-dir", cwd=path)
        common_dir = result.stdout.strip()
        if common_dir == ".git":
            # In main repo, resolve relative to toplevel
            repo_root = get_repo_root(path)
            return repo_root / ".git" if repo_root else None
        return Path(common_dir)
    except subprocess.CalledProcessError:
        return None


def get_main_repo_root(path: Path | None = None) -> Path | None:
    """Get the main repository root (even when in a worktree).

    Handles regular repos, worktrees, and submodules correctly.
    """
    common_dir = get_common_dir(path)
    if common_dir is None:
        return None
    # common_dir is /path/to/repo/.git, so parent is repo root
    if common_dir.name == ".git":
        return common_dir.parent
    # Check if we're in a submodule (common_dir is inside .git/modules/)
    # e.g., /path/to/parent/.git/modules/submodule-name
    parts = common_dir.parts
    for i, part in enumerate(parts[:-1]):
        if part == ".git" and parts[i + 1] == "modules":
            # For submodules, use --show-toplevel to get the submodule's working directory
            return get_repo_root(path)
    # For bare repos or unusual setups, try to go up from common_dir
    return common_dir.parent


def sanitize_branch_name(branch: str) -> str:
    """Sanitize a branch name for use as a directory name.

    Converts slashes, spaces, and other problematic characters to hyphens.
    """
    # Replace problematic characters with hyphens
    sanitized = re.sub(r'[\/\\ :*?"<>|#]', "-", branch)
    # Remove leading/trailing hyphens
    return sanitized.strip("-")


def get_default_branch(path: Path | None = None) -> str:
    """Get the default branch name (main or master)."""
    try:
        # Try to get from origin/HEAD
        result = _run_git(
            "symbolic-ref",
            "--quiet",
            "refs/remotes/origin/HEAD",
            cwd=path,
            check=False,
        )
        if result.returncode == 0:
            # refs/remotes/origin/main -> main
            return result.stdout.strip().replace("refs/remotes/origin/", "")
    except Exception:  # noqa: S110
        pass

    # Try common branch names
    for branch in ["main", "master"]:
        try:
            result = _run_git(
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/remotes/origin/{branch}",
                cwd=path,
                check=False,
            )
            if result.returncode == 0:
                return branch
        except Exception:  # noqa: S110
            pass

    return "main"  # Default fallback


def get_current_branch(path: Path | None = None) -> str | None:
    """Get the current branch name."""
    try:
        result = _run_git("branch", "--show-current", cwd=path, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        # Fallback for older git or detached HEAD
        result = _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=path, check=False)
        branch = result.stdout.strip()
        return None if branch == "HEAD" else branch
    except Exception:
        return None


@dataclass
class WorktreeInfo:
    """Information about a git worktree."""

    path: Path
    branch: str | None
    commit: str | None
    is_main: bool
    is_detached: bool
    is_locked: bool
    is_prunable: bool

    @property
    def name(self) -> str:
        """Get the worktree directory name."""
        return self.path.name


def list_worktrees(repo_path: Path | None = None) -> list[WorktreeInfo]:
    """List all worktrees for the repository."""
    worktrees: list[WorktreeInfo] = []

    try:
        result = _run_git("worktree", "list", "--porcelain", cwd=repo_path)
    except subprocess.CalledProcessError:
        return worktrees

    # Parse porcelain output
    current_wt: dict[str, str | bool] = {}

    for line in result.stdout.splitlines():
        if not line:
            # End of worktree entry
            if "worktree" in current_wt:
                wt_path = Path(str(current_wt["worktree"]))
                worktrees.append(
                    WorktreeInfo(
                        path=wt_path,
                        branch=str(current_wt.get("branch", "")).replace(
                            "refs/heads/",
                            "",
                        )
                        or None,
                        commit=str(current_wt.get("HEAD", "")) or None,
                        is_main=len(worktrees) == 0,  # First worktree is main
                        is_detached=current_wt.get("detached", False) is True,
                        is_locked=current_wt.get("locked", False) is True,
                        is_prunable=current_wt.get("prunable", False) is True,
                    ),
                )
            current_wt = {}
            continue

        if line.startswith("worktree "):
            current_wt["worktree"] = line[9:]
        elif line.startswith("HEAD "):
            current_wt["HEAD"] = line[5:]
        elif line.startswith("branch "):
            current_wt["branch"] = line[7:]
        elif line == "detached":
            current_wt["detached"] = True
        elif line.startswith("locked"):
            current_wt["locked"] = True
        elif line.startswith("prunable"):
            current_wt["prunable"] = True

    # Handle last entry if no trailing newline
    if "worktree" in current_wt:
        wt_path = Path(str(current_wt["worktree"]))
        worktrees.append(
            WorktreeInfo(
                path=wt_path,
                branch=str(current_wt.get("branch", "")).replace("refs/heads/", "") or None,
                commit=str(current_wt.get("HEAD", "")) or None,
                is_main=len(worktrees) == 0,
                is_detached=current_wt.get("detached", False) is True,
                is_locked=current_wt.get("locked", False) is True,
                is_prunable=current_wt.get("prunable", False) is True,
            ),
        )

    return worktrees


def resolve_worktree_base_dir(repo_root: Path) -> Path:
    """Resolve the base directory for worktrees.

    Default: <repo>-worktrees next to the repo.
    Can be configured via GTR_WORKTREES_DIR environment variable.
    """
    env_dir = os.environ.get("AGENT_SPACE_DIR") or os.environ.get("GTR_WORKTREES_DIR")
    if env_dir:
        base_dir = Path(env_dir).expanduser()
        if not base_dir.is_absolute():
            base_dir = repo_root / base_dir
        return base_dir

    # Default: sibling directory named <repo>-worktrees
    return repo_root.parent / f"{repo_root.name}-worktrees"


def find_worktree_by_name(
    name: str,
    repo_path: Path | None = None,
) -> WorktreeInfo | None:
    """Find a worktree by branch name or directory name."""
    worktrees = list_worktrees(repo_path)
    sanitized = sanitize_branch_name(name)

    for wt in worktrees:
        # Match by branch name
        if wt.branch == name:
            return wt
        # Match by directory name
        if wt.path.name in {sanitized, name}:
            return wt
        # Match by sanitized branch name
        if wt.branch and sanitize_branch_name(wt.branch) == sanitized:
            return wt

    return None


@dataclass
class CreateWorktreeResult:
    """Result of creating a worktree."""

    success: bool
    path: Path | None
    branch: str
    error: str | None = None
    warning: str | None = None


def _check_branch_exists(branch_name: str, repo_root: Path) -> tuple[bool, bool]:
    """Check if a branch exists remotely and/or locally.

    Returns:
        Tuple of (remote_exists, local_exists)

    """
    remote_exists = False
    local_exists = False

    try:
        result = _run_git(
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/remotes/origin/{branch_name}",
            cwd=repo_root,
            check=False,
        )
        remote_exists = result.returncode == 0
    except Exception:  # noqa: S110
        pass

    try:
        result = _run_git(
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch_name}",
            cwd=repo_root,
            check=False,
        )
        local_exists = result.returncode == 0
    except Exception:  # noqa: S110
        pass

    return remote_exists, local_exists


def _parse_git_config_regexp(output: str, prefix: str, suffix: str) -> list[tuple[str, str]]:
    """Parse git config --get-regexp output into (extracted_name, value) pairs."""
    results: list[tuple[str, str]] = []
    for line in output.strip().split("\n"):
        if not line or " " not in line:
            continue
        key, value = line.split(" ", 1)
        name = key.removeprefix(prefix).removesuffix(suffix)
        results.append((name, value))
    return results


def _init_submodules_recursive(
    repo_path: Path,
    ref_modules_dir: Path | None,
    on_log: Callable[[str], None] | None,
    capture_output: bool,
    depth: int = 0,
) -> None:
    """Recursively initialize submodules, using local clones when available."""
    if not (repo_path / ".gitmodules").exists():
        return

    # Register submodules in .git/config
    _run_git("submodule", "init", cwd=repo_path, check=False, capture_output=capture_output)

    # Get submodule names and URLs from config
    result = _run_git(
        "config",
        "--local",
        "--get-regexp",
        r"^submodule\..*\.url$",
        cwd=repo_path,
        check=False,
    )
    submodule_urls = _parse_git_config_regexp(result.stdout, "submodule.", ".url")
    if not submodule_urls:
        return

    # Get submodule paths from .gitmodules (name != path in some cases)
    # This is the canonical source - only submodules in .gitmodules should be initialized
    result = _run_git(
        "config",
        "--file",
        ".gitmodules",
        "--get-regexp",
        r"^submodule\..*\.path$",
        cwd=repo_path,
        check=False,
    )
    name_to_path = dict(_parse_git_config_regexp(result.stdout, "submodule.", ".path"))

    # Filter to only submodules that exist in .gitmodules (not stale config entries)
    submodule_urls = [(name, url) for name, url in submodule_urls if name in name_to_path]
    if not submodule_urls:
        return

    # Override URLs to local paths where available, track for restoration
    overrides: list[tuple[str, str]] = []  # (name, original_url)
    for name, original_url in submodule_urls:
        if ref_modules_dir is None:
            continue
        local_module = ref_modules_dir / name
        if not local_module.exists():
            continue
        overrides.append((name, original_url))
        _run_git("config", f"submodule.{name}.url", str(local_module), cwd=repo_path, check=False)
        if on_log:
            on_log(f"{'  ' * depth}Using local clone for {name}")

    # Clone submodules (NOT recursive - we'll handle children ourselves)
    _run_git(
        "submodule",
        "update",
        cwd=repo_path,
        check=False,
        capture_output=capture_output,
        allow_file_protocol=bool(overrides),
    )

    # Restore original URLs for future remote fetches
    for name, original_url in overrides:
        _run_git("config", f"submodule.{name}.url", original_url, cwd=repo_path, check=False)

    # Recursively initialize nested submodules
    for name, _original_url in submodule_urls:
        child_repo = repo_path / name_to_path.get(name, name)
        if not child_repo.exists():
            continue
        child_ref = ref_modules_dir / name / "modules" if ref_modules_dir else None
        if child_ref and not child_ref.exists():
            child_ref = None
        _init_submodules_recursive(child_repo, child_ref, on_log, capture_output, depth + 1)


def _init_submodules(
    worktree_path: Path,
    *,
    reference_repo: Path | None = None,
    on_log: Callable[[str], None] | None = None,
    capture_output: bool = True,
) -> None:
    """Initialize git submodules in a worktree, using local clones when available."""
    if not (worktree_path / ".gitmodules").exists():
        return

    if on_log:
        on_log("Initializing submodules...")

    # Get reference repo's git dir for local submodule clones
    ref_modules_dir: Path | None = None
    if reference_repo is not None:
        result = _run_git("rev-parse", "--git-dir", cwd=reference_repo, check=False)
        if result.returncode == 0:
            ref_git_dir = Path(result.stdout.strip())
            if not ref_git_dir.is_absolute():
                ref_git_dir = reference_repo / ref_git_dir
            ref_modules_dir = ref_git_dir / "modules"

    _init_submodules_recursive(
        worktree_path,
        ref_modules_dir,
        on_log,
        capture_output,
    )


def _pull_lfs(
    worktree_path: Path,
    *,
    on_log: Callable[[str], None] | None = None,
    capture_output: bool = True,
) -> None:
    """Pull Git LFS files in a worktree if LFS is used.

    Evidence: https://git-lfs.com/ - `git lfs pull` fetches LFS objects.
    This is a no-op if LFS is not used or files are already present.
    """
    # Check if .gitattributes contains LFS filters
    gitattributes = worktree_path / ".gitattributes"
    if not gitattributes.exists():
        return

    if "filter=lfs" not in gitattributes.read_text():
        return

    # Check if git-lfs is installed
    if not shutil.which("git-lfs"):
        return

    if on_log:
        on_log("Pulling Git LFS files...")

    _run_git("lfs", "pull", cwd=worktree_path, check=False, capture_output=capture_output)


def _add_worktree(
    branch_name: str,
    worktree_path: Path,
    repo_root: Path,
    from_ref: str,
    *,
    remote_exists: bool,
    local_exists: bool,
    force: bool,
    on_log: Callable[[str], None] | None,
    capture_output: bool = True,
) -> None:
    """Add a git worktree, handling different branch scenarios."""
    force_flag = ["--force"] if force else []

    if remote_exists and not local_exists:
        # Remote branch exists, create tracking branch
        if on_log:
            on_log(f"Running: git branch --track {branch_name} origin/{branch_name}")
        _run_git(
            "branch",
            "--track",
            branch_name,
            f"origin/{branch_name}",
            cwd=repo_root,
            check=False,
            capture_output=capture_output,
        )
        if on_log:
            on_log(f"Running: git worktree add {worktree_path} {branch_name}")
        _run_git(
            "worktree",
            "add",
            *force_flag,
            str(worktree_path),
            branch_name,
            cwd=repo_root,
            capture_output=capture_output,
        )
    elif local_exists:
        # Local branch exists
        if on_log:
            on_log(f"Running: git worktree add {worktree_path} {branch_name}")
        _run_git(
            "worktree",
            "add",
            *force_flag,
            str(worktree_path),
            branch_name,
            cwd=repo_root,
            capture_output=capture_output,
        )
    else:
        # Create new branch from ref
        if on_log:
            on_log(f"Running: git worktree add -b {branch_name} {worktree_path} {from_ref}")
        _run_git(
            "worktree",
            "add",
            *force_flag,
            str(worktree_path),
            "-b",
            branch_name,
            from_ref,
            cwd=repo_root,
            capture_output=capture_output,
        )


def create_worktree(
    branch_name: str,
    *,
    repo_path: Path | None = None,
    from_ref: str | None = None,
    base_dir: Path | None = None,
    prefix: str = "",
    force: bool = False,
    fetch: bool = True,
    on_log: Callable[[str], None] | None = None,
    capture_output: bool = True,
) -> CreateWorktreeResult:
    """Create a new git worktree.

    Args:
        branch_name: The branch name for the worktree
        repo_path: Path to the repository (default: current directory)
        from_ref: Reference to create the branch from (default: default branch)
        base_dir: Base directory for worktrees (default: auto-resolved)
        prefix: Prefix for the worktree directory name
        force: Allow same branch in multiple worktrees
        fetch: Fetch from origin before creating
        on_log: Optional callback for logging status messages
        capture_output: Whether to capture command output (False to stream)

    Returns:
        CreateWorktreeResult with success status and path or error

    """
    repo_root = get_main_repo_root(repo_path)
    if repo_root is None:
        return CreateWorktreeResult(
            success=False,
            path=None,
            branch=branch_name,
            error="Not in a git repository",
        )

    if base_dir is None:
        base_dir = resolve_worktree_base_dir(repo_root)

    sanitized_name = sanitize_branch_name(branch_name)
    worktree_path = base_dir / f"{prefix}{sanitized_name}"

    # Check if worktree already exists
    if worktree_path.exists():
        return CreateWorktreeResult(
            success=False,
            path=worktree_path,
            branch=branch_name,
            error=f"Worktree already exists at {worktree_path}",
        )

    # Create base directory if needed
    base_dir.mkdir(parents=True, exist_ok=True)

    # Check if origin remote exists
    origin_exists = has_origin_remote(repo_root)

    # Fetch latest refs (only if origin exists)
    if fetch and origin_exists:
        if on_log:
            on_log("Running: git fetch origin")
        _run_git("fetch", "origin", cwd=repo_root, check=False, capture_output=capture_output)

    # Track if user explicitly provided --from (for warning generation)
    from_ref_explicit = from_ref is not None

    # Determine the reference to create from
    # Use origin/{branch} if origin exists, otherwise use local branch
    if from_ref is None:
        default_branch = get_default_branch(repo_root)
        from_ref = f"origin/{default_branch}" if origin_exists else default_branch

    # Check if branch exists remotely or locally
    remote_exists, local_exists = _check_branch_exists(branch_name, repo_root)

    # Generate warning if --from was specified but will be ignored
    warning: str | None = None
    if from_ref_explicit and (local_exists or remote_exists):
        warning = (
            f"Branch '{branch_name}' already exists. "
            f"Using existing branch instead of creating from '{from_ref}'."
        )

    try:
        _add_worktree(
            branch_name,
            worktree_path,
            repo_root,
            from_ref,
            remote_exists=remote_exists,
            local_exists=local_exists,
            force=force,
            on_log=on_log,
            capture_output=capture_output,
        )

        # Initialize submodules in the new worktree, using main repo as reference
        # to avoid re-fetching objects that already exist locally
        _init_submodules(
            worktree_path,
            reference_repo=repo_root,
            on_log=on_log,
            capture_output=capture_output,
        )

        # Pull Git LFS files if the repo uses LFS
        _pull_lfs(
            worktree_path,
            on_log=on_log,
            capture_output=capture_output,
        )

        return CreateWorktreeResult(
            success=True,
            path=worktree_path,
            branch=branch_name,
            warning=warning,
        )

    except subprocess.CalledProcessError as e:
        return CreateWorktreeResult(
            success=False,
            path=worktree_path,
            branch=branch_name,
            error=e.stderr.strip() if e.stderr else str(e),
        )


def remove_worktree(
    worktree_path: Path,
    *,
    force: bool = False,
    delete_branch: bool = False,
    repo_path: Path | None = None,
) -> tuple[bool, str | None]:
    """Remove a git worktree.

    Args:
        worktree_path: Path to the worktree to remove
        force: Force removal even with uncommitted changes
        delete_branch: Also delete the branch
        repo_path: Path to the main repository

    Returns:
        Tuple of (success, error_message)

    """
    if not worktree_path.exists():
        return False, f"Worktree not found at {worktree_path}"

    repo_root = get_main_repo_root(repo_path)
    if repo_root is None:
        return False, "Not in a git repository"

    # Get branch name before removing
    branch_name = get_current_branch(worktree_path)

    force_flag = ["--force"] if force else []

    try:
        _run_git(
            "worktree",
            "remove",
            *force_flag,
            str(worktree_path),
            cwd=repo_root,
        )
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip() if e.stderr else str(e)

    # Delete branch if requested
    if delete_branch and branch_name:
        with contextlib.suppress(Exception):
            _run_git(
                "branch",
                "-D" if force else "-d",
                branch_name,
                cwd=repo_root,
                check=False,
            )

    return True, None


def prune_worktrees(repo_path: Path | None = None) -> None:
    """Prune stale worktree references."""
    repo_root = get_main_repo_root(repo_path)
    if repo_root:
        _run_git("worktree", "prune", cwd=repo_root, check=False)


@dataclass
class WorktreeStatus:
    """Git status information for a worktree."""

    modified: int  # Files modified but not staged
    staged: int  # Files staged for commit
    untracked: int  # Untracked files
    ahead: int  # Commits ahead of upstream
    behind: int  # Commits behind upstream
    last_commit_time: str | None  # Relative time of last commit (e.g., "2 hours ago")
    last_commit_timestamp: int | None  # Unix timestamp of last commit


def _parse_porcelain_status(output: str) -> tuple[int, int, int]:
    """Parse git status --porcelain output into (modified, staged, untracked) counts."""
    modified = 0
    staged = 0
    untracked = 0

    for line in output.splitlines():
        if len(line) < 2:  # noqa: PLR2004
            continue
        index_status = line[0]
        worktree_status = line[1]

        # Untracked files
        if index_status == "?" and worktree_status == "?":
            untracked += 1
        else:
            # Staged changes (index has modification)
            if index_status in "MADRCU":
                staged += 1
            # Worktree changes (not staged)
            if worktree_status in "MADRCU":
                modified += 1

    return modified, staged, untracked


def _parse_ahead_behind(output: str) -> tuple[int, int]:
    """Parse git rev-list --left-right --count output into (ahead, behind) counts."""
    parts = output.strip().split()
    if len(parts) == 2:  # noqa: PLR2004
        return int(parts[1]), int(parts[0])  # ahead, behind
    return 0, 0


def get_worktree_status(worktree_path: Path) -> WorktreeStatus | None:
    """Get git status information for a worktree.

    Returns None if the worktree doesn't exist or isn't a valid git repo.
    """
    if not worktree_path.exists():
        return None

    # Get porcelain status for file counts
    result = _run_git("status", "--porcelain", cwd=worktree_path, check=False)
    modified, staged, untracked = (
        _parse_porcelain_status(result.stdout) if result.returncode == 0 else (0, 0, 0)
    )

    # Get ahead/behind counts
    result = _run_git(
        "rev-list",
        "--left-right",
        "--count",
        "@{upstream}...HEAD",
        cwd=worktree_path,
        check=False,
    )
    ahead, behind = _parse_ahead_behind(result.stdout) if result.returncode == 0 else (0, 0)

    # Get last commit time
    last_commit_time = None
    last_commit_timestamp = None

    result = _run_git("log", "-1", "--format=%ar", cwd=worktree_path, check=False)
    if result.returncode == 0 and result.stdout.strip():
        last_commit_time = result.stdout.strip()

    result = _run_git("log", "-1", "--format=%at", cwd=worktree_path, check=False)
    if result.returncode == 0 and result.stdout.strip():
        last_commit_timestamp = int(result.stdout.strip())

    return WorktreeStatus(
        modified=modified,
        staged=staged,
        untracked=untracked,
        ahead=ahead,
        behind=behind,
        last_commit_time=last_commit_time,
        last_commit_timestamp=last_commit_timestamp,
    )
