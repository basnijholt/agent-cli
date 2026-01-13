"""Tests for git worktree operations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest  # noqa: TC002

from agent_cli.dev.worktree import (
    WorktreeInfo,
    _parse_git_config_regexp,
    find_worktree_by_name,
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
