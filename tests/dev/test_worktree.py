"""Tests for git worktree operations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest  # noqa: TC002

from agent_cli.dev.worktree import (
    CreateWorktreeResult,
    WorktreeInfo,
    _parse_git_config_regexp,
    _pull_lfs,
    create_worktree,
    find_worktree_by_name,
    get_main_repo_root,
    has_origin_remote,
    list_worktrees,
    resolve_worktree_base_dir,
    sanitize_branch_name,
)


class TestSanitizeBranchName:
    """Tests for sanitize_branch_name function."""

    def test_simple_name(self) -> None:
        """Simple name passes through."""
        assert sanitize_branch_name("feature") == "feature"

    def test_slashes_to_hyphens(self) -> None:
        """Slashes are converted to hyphens."""
        assert sanitize_branch_name("feature/add-login") == "feature-add-login"

    def test_spaces_to_hyphens(self) -> None:
        """Spaces are converted to hyphens."""
        assert sanitize_branch_name("my feature") == "my-feature"

    def test_special_chars_to_hyphens(self) -> None:
        """Special characters are converted to hyphens."""
        assert sanitize_branch_name('test:name*with"chars') == "test-name-with-chars"

    def test_strips_leading_trailing_hyphens(self) -> None:
        """Leading and trailing hyphens are stripped."""
        assert sanitize_branch_name("/feature/") == "feature"

    def test_multiple_consecutive_hyphens(self) -> None:
        """Multiple slashes become multiple hyphens."""
        result = sanitize_branch_name("a//b")
        assert result == "a--b"


class TestResolveWorktreeBaseDir:
    """Tests for resolve_worktree_base_dir function."""

    def test_default_sibling_directory(self, tmp_path: Path) -> None:
        """Default is sibling directory named <repo>-worktrees."""
        repo_root = tmp_path / "my-repo"
        repo_root.mkdir()
        result = resolve_worktree_base_dir(repo_root)
        assert result == tmp_path / "my-repo-worktrees"

    def test_agent_space_dir_env_absolute(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AGENT_SPACE_DIR with absolute path."""
        custom_dir = tmp_path / "custom-worktrees"
        monkeypatch.setenv("AGENT_SPACE_DIR", str(custom_dir))
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        result = resolve_worktree_base_dir(repo_root)
        assert result == custom_dir

    def test_agent_space_dir_env_relative(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AGENT_SPACE_DIR with relative path."""
        monkeypatch.setenv("AGENT_SPACE_DIR", "worktrees")
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        result = resolve_worktree_base_dir(repo_root)
        assert result == repo_root / "worktrees"

    def test_gtr_worktrees_dir_env(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GTR_WORKTREES_DIR is also supported (compatibility)."""
        custom_dir = tmp_path / "gtr-worktrees"
        monkeypatch.setenv("GTR_WORKTREES_DIR", str(custom_dir))
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        result = resolve_worktree_base_dir(repo_root)
        assert result == custom_dir

    def test_agent_space_dir_takes_priority(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """AGENT_SPACE_DIR takes priority over GTR_WORKTREES_DIR."""
        monkeypatch.setenv("AGENT_SPACE_DIR", str(tmp_path / "agent"))
        monkeypatch.setenv("GTR_WORKTREES_DIR", str(tmp_path / "gtr"))
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        result = resolve_worktree_base_dir(repo_root)
        assert result == tmp_path / "agent"


class TestGetMainRepoRoot:
    """Tests for get_main_repo_root function."""

    def test_regular_repo(self, tmp_path: Path) -> None:
        """Regular repo returns parent of .git directory."""
        mock_common_dir = MagicMock()
        mock_common_dir.return_value = tmp_path / "repo" / ".git"

        with patch("agent_cli.dev.worktree.get_common_dir", mock_common_dir):
            result = get_main_repo_root(tmp_path / "repo")

        assert result == tmp_path / "repo"

    def test_submodule_uses_show_toplevel(self) -> None:
        """Submodule (common_dir inside .git/modules/) uses --show-toplevel.

        When working inside a git submodule, git rev-parse --git-common-dir
        returns a path like /path/to/parent/.git/modules/submodule-name.
        In this case, we should use --show-toplevel instead of just taking
        the parent directory, which would incorrectly return .git/modules/.

        This was a bug where submodules returned common_dir.parent which
        pointed to .git/modules/ instead of the actual submodule directory.
        """
        submodule_common_dir = Path("/opt/parent/.git/modules/my-submodule")
        submodule_toplevel = Path("/opt/parent/my-submodule")

        mock_common_dir = MagicMock(return_value=submodule_common_dir)
        mock_repo_root = MagicMock(return_value=submodule_toplevel)

        with (
            patch("agent_cli.dev.worktree.get_common_dir", mock_common_dir),
            patch("agent_cli.dev.worktree.get_repo_root", mock_repo_root),
        ):
            result = get_main_repo_root(Path("/opt/parent/my-submodule"))

        # Should use get_repo_root for submodules, not common_dir.parent
        mock_repo_root.assert_called_once()
        assert result == submodule_toplevel
        assert ".git/modules" not in str(result)


class TestListWorktrees:
    """Tests for list_worktrees function."""

    def test_parse_porcelain_output(self) -> None:
        """Parse git worktree list --porcelain output."""
        porcelain_output = """worktree /path/to/main
HEAD abc123
branch refs/heads/main

worktree /path/to/feature
HEAD def456
branch refs/heads/feature-branch

"""
        mock_run = MagicMock()
        mock_run.return_value.stdout = porcelain_output
        mock_run.return_value.returncode = 0

        with patch("agent_cli.dev.worktree._run_git", mock_run):
            worktrees = list_worktrees(Path("/repo"))

        assert len(worktrees) == 2
        assert worktrees[0].path == Path("/path/to/main")
        assert worktrees[0].branch == "main"
        assert worktrees[0].is_main is True
        assert worktrees[1].path == Path("/path/to/feature")
        assert worktrees[1].branch == "feature-branch"
        assert worktrees[1].is_main is False

    def test_parse_detached_head(self) -> None:
        """Parse worktree with detached HEAD."""
        porcelain_output = """worktree /path/to/main
HEAD abc123
branch refs/heads/main

worktree /path/to/detached
HEAD def456
detached

"""
        mock_run = MagicMock()
        mock_run.return_value.stdout = porcelain_output

        with patch("agent_cli.dev.worktree._run_git", mock_run):
            worktrees = list_worktrees(Path("/repo"))

        assert len(worktrees) == 2
        assert worktrees[1].is_detached is True
        assert worktrees[1].branch is None

    def test_parse_locked_worktree(self) -> None:
        """Parse locked worktree."""
        porcelain_output = """worktree /path/to/main
HEAD abc123
branch refs/heads/main

worktree /path/to/locked
HEAD def456
branch refs/heads/locked-branch
locked

"""
        mock_run = MagicMock()
        mock_run.return_value.stdout = porcelain_output

        with patch("agent_cli.dev.worktree._run_git", mock_run):
            worktrees = list_worktrees(Path("/repo"))

        assert worktrees[1].is_locked is True


class TestFindWorktreeByName:
    """Tests for find_worktree_by_name function."""

    def test_find_by_branch_name(self) -> None:
        """Find worktree by exact branch name."""
        worktrees = [
            WorktreeInfo(
                path=Path("/path/to/main"),
                branch="main",
                commit="abc",
                is_main=True,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
            WorktreeInfo(
                path=Path("/path/to/feature"),
                branch="my-feature",
                commit="def",
                is_main=False,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
        ]

        with patch("agent_cli.dev.worktree.list_worktrees", return_value=worktrees):
            result = find_worktree_by_name("my-feature", Path("/repo"))

        assert result is not None
        assert result.branch == "my-feature"

    def test_find_by_directory_name(self) -> None:
        """Find worktree by directory name."""
        worktrees = [
            WorktreeInfo(
                path=Path("/path/to/feature-dir"),
                branch="feature/some-branch",
                commit="abc",
                is_main=False,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
        ]

        with patch("agent_cli.dev.worktree.list_worktrees", return_value=worktrees):
            result = find_worktree_by_name("feature-dir", Path("/repo"))

        assert result is not None
        assert result.path.name == "feature-dir"

    def test_find_by_sanitized_branch(self) -> None:
        """Find worktree by sanitized branch name."""
        worktrees = [
            WorktreeInfo(
                path=Path("/path/to/feature-branch"),
                branch="feature/branch",
                commit="abc",
                is_main=False,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
        ]

        with patch("agent_cli.dev.worktree.list_worktrees", return_value=worktrees):
            result = find_worktree_by_name("feature-branch", Path("/repo"))

        assert result is not None

    def test_not_found(self) -> None:
        """Return None when worktree not found."""
        with patch("agent_cli.dev.worktree.list_worktrees", return_value=[]):
            result = find_worktree_by_name("nonexistent", Path("/repo"))

        assert result is None


class TestWorktreeInfo:
    """Tests for WorktreeInfo dataclass."""

    def test_name_property(self) -> None:
        """Name property returns directory name."""
        wt = WorktreeInfo(
            path=Path("/some/long/path/to/my-worktree"),
            branch="my-branch",
            commit="abc",
            is_main=False,
            is_detached=False,
            is_locked=False,
            is_prunable=False,
        )
        assert wt.name == "my-worktree"


class TestParseGitConfigRegexp:
    """Tests for _parse_git_config_regexp function.

    Based on real git config --get-regexp output from a repo with nested submodules:
    - main-repo -> libs/middle (submodule) -> vendor/deep (nested submodule)
    """

    def test_parse_submodule_urls(self) -> None:
        r"""Parse submodule URL config output.

        Real output from: git config --local --get-regexp '^submodule\..*\.url$'
        """
        output = "submodule.libs/middle.url /home/user/test-fixture/middle-lib"
        result = _parse_git_config_regexp(output, "submodule.", ".url")
        assert result == [("libs/middle", "/home/user/test-fixture/middle-lib")]

    def test_parse_submodule_paths(self) -> None:
        r"""Parse submodule path config output.

        Real output from: git config --file .gitmodules --get-regexp '^submodule\..*\.path$'
        """
        output = "submodule.libs/middle.path libs/middle"
        result = _parse_git_config_regexp(output, "submodule.", ".path")
        assert result == [("libs/middle", "libs/middle")]

    def test_parse_nested_submodule(self) -> None:
        """Parse nested submodule config.

        Real output from nested submodule (libs/middle) with its own submodule (vendor/deep).
        """
        output = "submodule.vendor/deep.url /home/user/test-fixture/deep-lib"
        result = _parse_git_config_regexp(output, "submodule.", ".url")
        assert result == [("vendor/deep", "/home/user/test-fixture/deep-lib")]

    def test_parse_multiple_submodules(self) -> None:
        """Parse multiple submodules in output."""
        output = (
            "submodule.libs/foo.url /path/to/foo\n"
            "submodule.libs/bar.url /path/to/bar\n"
            "submodule.vendor/baz.url /path/to/baz"
        )
        result = _parse_git_config_regexp(output, "submodule.", ".url")
        assert result == [
            ("libs/foo", "/path/to/foo"),
            ("libs/bar", "/path/to/bar"),
            ("vendor/baz", "/path/to/baz"),
        ]

    def test_parse_url_with_spaces(self) -> None:
        """Parse URL containing spaces (uses split(' ', 1))."""
        output = "submodule.mylib.url /path/with spaces/to/repo"
        result = _parse_git_config_regexp(output, "submodule.", ".url")
        assert result == [("mylib", "/path/with spaces/to/repo")]

    def test_parse_submodule_name_with_dots(self) -> None:
        """Parse submodule name containing dots.

        The name 'foo.bar' results in config key 'submodule.foo.bar.url'.
        removeprefix/removesuffix correctly extracts 'foo.bar'.
        """
        output = "submodule.foo.bar.url /path/to/foobar"
        result = _parse_git_config_regexp(output, "submodule.", ".url")
        assert result == [("foo.bar", "/path/to/foobar")]

    def test_parse_empty_output(self) -> None:
        """Handle empty output (no submodules)."""
        result = _parse_git_config_regexp("", "submodule.", ".url")
        assert result == []

    def test_parse_whitespace_only_output(self) -> None:
        """Handle whitespace-only output."""
        result = _parse_git_config_regexp("  \n  \n  ", "submodule.", ".url")
        assert result == []

    def test_parse_malformed_line_no_space(self) -> None:
        """Skip malformed lines without space separator."""
        output = "submodule.broken.url\nsubmodule.valid.url /path/to/valid"
        result = _parse_git_config_regexp(output, "submodule.", ".url")
        assert result == [("valid", "/path/to/valid")]


class TestCreateWorktreeResult:
    """Tests for CreateWorktreeResult and warning field."""

    def test_warning_field_default_none(self) -> None:
        """CreateWorktreeResult.warning defaults to None."""
        result = CreateWorktreeResult(success=True, path=Path("/test"), branch="test")
        assert result.warning is None

    def test_warning_field_can_be_set(self) -> None:
        """CreateWorktreeResult.warning can be set."""
        result = CreateWorktreeResult(
            success=True,
            path=Path("/test"),
            branch="test",
            warning="Test warning",
        )
        assert result.warning == "Test warning"


class TestCreateWorktreeFromRefWarning:
    """Tests for --from flag warning when branch already exists.

    Bug fix: When --from is specified but the branch already exists,
    the user should be warned that --from is being ignored and the
    existing branch is used instead.

    Evidence: create_worktree() now tracks whether from_ref was explicitly
    provided and generates a warning when the branch already exists locally
    or remotely.
    """

    def test_warning_when_local_branch_exists_and_from_specified(self) -> None:
        """Warning is generated when local branch exists and --from is specified."""
        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch(
                "agent_cli.dev.worktree.resolve_worktree_base_dir",
                return_value=Path("/worktrees"),
            ),
            patch("agent_cli.dev.worktree._run_git") as mock_run,
            patch("agent_cli.dev.worktree._check_branch_exists", return_value=(False, True)),
            patch("agent_cli.dev.worktree._add_worktree"),
            patch("agent_cli.dev.worktree._init_submodules"),
            patch("agent_cli.dev.worktree._pull_lfs"),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir"),
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""

            result = create_worktree(
                "my-branch",
                repo_path=Path("/repo"),
                from_ref="feat/other-branch",  # Explicitly specified
                fetch=False,
            )

            assert result.success is True
            assert result.warning is not None
            assert "my-branch" in result.warning
            assert "already exists" in result.warning
            assert "feat/other-branch" in result.warning

    def test_warning_when_remote_branch_exists_and_from_specified(self) -> None:
        """Warning is generated when remote branch exists and --from is specified."""
        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch(
                "agent_cli.dev.worktree.resolve_worktree_base_dir",
                return_value=Path("/worktrees"),
            ),
            patch("agent_cli.dev.worktree._run_git") as mock_run,
            patch("agent_cli.dev.worktree._check_branch_exists", return_value=(True, False)),
            patch("agent_cli.dev.worktree._add_worktree"),
            patch("agent_cli.dev.worktree._init_submodules"),
            patch("agent_cli.dev.worktree._pull_lfs"),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir"),
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""

            result = create_worktree(
                "my-branch",
                repo_path=Path("/repo"),
                from_ref="origin/main",  # Explicitly specified
                fetch=False,
            )

            assert result.success is True
            assert result.warning is not None
            assert "already exists" in result.warning

    def test_no_warning_when_from_not_specified(self) -> None:
        """No warning when --from is not specified (uses default)."""
        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch(
                "agent_cli.dev.worktree.resolve_worktree_base_dir",
                return_value=Path("/worktrees"),
            ),
            patch("agent_cli.dev.worktree._run_git") as mock_run,
            patch("agent_cli.dev.worktree._check_branch_exists", return_value=(False, True)),
            patch("agent_cli.dev.worktree._add_worktree"),
            patch("agent_cli.dev.worktree._init_submodules"),
            patch("agent_cli.dev.worktree.get_default_branch", return_value="main"),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir"),
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""

            result = create_worktree(
                "my-branch",
                repo_path=Path("/repo"),
                from_ref=None,  # Not specified, uses default
                fetch=False,
            )

            assert result.success is True
            assert result.warning is None  # No warning since --from wasn't explicit

    def test_no_warning_when_branch_is_new(self) -> None:
        """No warning when branch doesn't exist (will be created from --from)."""
        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch(
                "agent_cli.dev.worktree.resolve_worktree_base_dir",
                return_value=Path("/worktrees"),
            ),
            patch("agent_cli.dev.worktree._run_git") as mock_run,
            patch("agent_cli.dev.worktree._check_branch_exists", return_value=(False, False)),
            patch("agent_cli.dev.worktree._add_worktree"),
            patch("agent_cli.dev.worktree._init_submodules"),
            patch("agent_cli.dev.worktree._pull_lfs"),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir"),
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""

            result = create_worktree(
                "new-branch",
                repo_path=Path("/repo"),
                from_ref="feat/other-branch",  # Explicitly specified
                fetch=False,
            )

            assert result.success is True
            assert result.warning is None  # No warning since branch is new


class TestPullLfs:
    """Tests for _pull_lfs function.

    Evidence: https://git-lfs.com/ - Git LFS stores large files outside the repo
    and replaces them with pointers. `git lfs pull` fetches the actual content.
    """

    def test_no_gitattributes(self, tmp_path: Path) -> None:
        """Skip LFS pull when .gitattributes doesn't exist."""
        # No .gitattributes file
        logged: list[str] = []
        _pull_lfs(tmp_path, on_log=logged.append)
        assert logged == []  # No log means no action taken

    def test_no_lfs_filter_in_gitattributes(self, tmp_path: Path) -> None:
        """Skip LFS pull when .gitattributes doesn't contain filter=lfs."""
        (tmp_path / ".gitattributes").write_text("*.txt text\n")
        logged: list[str] = []
        _pull_lfs(tmp_path, on_log=logged.append)
        assert logged == []  # No log means no action taken

    def test_lfs_pull_when_filter_present(self, tmp_path: Path) -> None:
        """Run git lfs pull when filter=lfs is in .gitattributes."""
        (tmp_path / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n")

        with (
            patch("agent_cli.dev.worktree.shutil.which", return_value="/usr/bin/git-lfs"),
            patch("agent_cli.dev.worktree._run_git") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            logged: list[str] = []
            _pull_lfs(tmp_path, on_log=logged.append)

            assert "Pulling Git LFS files..." in logged
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0] == ("lfs", "pull")

    def test_skip_when_git_lfs_not_installed(self, tmp_path: Path) -> None:
        """Skip LFS pull when git-lfs is not installed."""
        (tmp_path / ".gitattributes").write_text("*.bin filter=lfs diff=lfs merge=lfs -text\n")

        with patch("agent_cli.dev.worktree.shutil.which", return_value=None):
            logged: list[str] = []
            _pull_lfs(tmp_path, on_log=logged.append)
            assert logged == []  # No log means no action taken


class TestHasOriginRemote:
    """Tests for has_origin_remote function.

    Validates detection of origin remote presence using `git remote get-url origin`.
    """

    def test_origin_exists(self) -> None:
        """Return True when origin remote is configured."""
        mock_run = MagicMock()
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "https://github.com/user/repo.git"

        with patch("agent_cli.dev.worktree._run_git", mock_run):
            assert has_origin_remote(Path("/repo")) is True

        mock_run.assert_called_once_with(
            "remote",
            "get-url",
            "origin",
            cwd=Path("/repo"),
            check=False,
        )

    def test_origin_not_exists(self) -> None:
        """Return False when origin remote is not configured."""
        mock_run = MagicMock()
        mock_run.return_value.returncode = 2  # git returns non-zero when remote doesn't exist
        mock_run.return_value.stdout = ""

        with patch("agent_cli.dev.worktree._run_git", mock_run):
            assert has_origin_remote(Path("/repo")) is False

    def test_git_command_fails(self) -> None:
        """Return False when git command raises exception."""
        with patch(
            "agent_cli.dev.worktree._run_git",
            side_effect=Exception("git not found"),
        ):
            assert has_origin_remote(Path("/repo")) is False


class TestCreateWorktreeNoOrigin:
    """Tests for create_worktree when repository has no origin remote.

    Bug fix: When a repository has no origin remote configured,
    `dev new` would fail with "fatal: invalid reference: origin/main"
    because it tried to create the worktree from origin/{branch}.

    The fix:
    1. Skip `git fetch origin` when no origin exists
    2. Use the local default branch instead of origin/{branch} as the base ref
    """

    def test_uses_local_branch_when_no_origin(self) -> None:
        """Use local branch as from_ref when no origin remote exists."""
        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch(
                "agent_cli.dev.worktree.resolve_worktree_base_dir",
                return_value=Path("/worktrees"),
            ),
            patch("agent_cli.dev.worktree._run_git") as mock_run,
            patch("agent_cli.dev.worktree._check_branch_exists", return_value=(False, False)),
            patch("agent_cli.dev.worktree._add_worktree") as mock_add_worktree,
            patch("agent_cli.dev.worktree._init_submodules"),
            patch("agent_cli.dev.worktree.get_default_branch", return_value="main"),
            patch("agent_cli.dev.worktree.has_origin_remote", return_value=False),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir"),
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""

            result = create_worktree(
                "new-branch",
                repo_path=Path("/repo"),
                from_ref=None,  # Auto-determine
                fetch=True,
            )

            assert result.success is True
            # Verify that _add_worktree was called with local "main" branch, not "origin/main"
            mock_add_worktree.assert_called_once()
            call_args = mock_add_worktree.call_args
            from_ref_used = call_args[0][3]  # 4th positional arg is from_ref
            assert from_ref_used == "main", f"Expected 'main', got '{from_ref_used}'"
            assert "origin" not in from_ref_used

    def test_skips_fetch_when_no_origin(self) -> None:
        """Skip git fetch when no origin remote exists."""
        fetch_called: list[tuple[str, ...]] = []

        def mock_run_git(*args: str, **_kwargs: object) -> MagicMock:
            if args[0] == "fetch":
                fetch_called.append(args)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch(
                "agent_cli.dev.worktree.resolve_worktree_base_dir",
                return_value=Path("/worktrees"),
            ),
            patch("agent_cli.dev.worktree._run_git", side_effect=mock_run_git),
            patch("agent_cli.dev.worktree._check_branch_exists", return_value=(False, False)),
            patch("agent_cli.dev.worktree._add_worktree"),
            patch("agent_cli.dev.worktree._init_submodules"),
            patch("agent_cli.dev.worktree.get_default_branch", return_value="main"),
            patch("agent_cli.dev.worktree.has_origin_remote", return_value=False),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir"),
        ):
            result = create_worktree(
                "new-branch",
                repo_path=Path("/repo"),
                from_ref=None,
                fetch=True,  # Fetch is requested but should be skipped
            )

            assert result.success is True
            assert len(fetch_called) == 0, "git fetch should not be called when no origin"

    def test_uses_origin_when_available(self) -> None:
        """Use origin/{branch} as from_ref when origin remote exists."""
        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch(
                "agent_cli.dev.worktree.resolve_worktree_base_dir",
                return_value=Path("/worktrees"),
            ),
            patch("agent_cli.dev.worktree._run_git") as mock_run,
            patch("agent_cli.dev.worktree._check_branch_exists", return_value=(False, False)),
            patch("agent_cli.dev.worktree._add_worktree") as mock_add_worktree,
            patch("agent_cli.dev.worktree._init_submodules"),
            patch("agent_cli.dev.worktree.get_default_branch", return_value="main"),
            patch("agent_cli.dev.worktree.has_origin_remote", return_value=True),
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.mkdir"),
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""

            result = create_worktree(
                "new-branch",
                repo_path=Path("/repo"),
                from_ref=None,  # Auto-determine
                fetch=True,
            )

            assert result.success is True
            # Verify that _add_worktree was called with "origin/main"
            mock_add_worktree.assert_called_once()
            call_args = mock_add_worktree.call_args
            from_ref_used = call_args[0][3]  # 4th positional arg is from_ref
            assert from_ref_used == "origin/main", f"Expected 'origin/main', got '{from_ref_used}'"
