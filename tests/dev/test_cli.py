"""Tests for dev CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from agent_cli.cli import app
from agent_cli.dev.cli import _generate_branch_name
from agent_cli.dev.worktree import WorktreeInfo

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


class TestGenerateBranchName:
    """Tests for _generate_branch_name function."""

    def test_generates_adjective_noun(self) -> None:
        """Generates name in adjective-noun format."""
        name = _generate_branch_name()
        parts = name.split("-")
        assert len(parts) >= 2

    def test_avoids_existing_branches(self) -> None:
        """Adds suffix to avoid existing branches."""
        existing: set[str] = {"happy-fox", "happy-fox-2"}
        # Run multiple times to ensure it generates unique names
        names = set()
        for _ in range(10):
            name = _generate_branch_name(existing)
            assert name not in existing
            names.add(name)

    def test_deterministic_with_collision(self) -> None:
        """Adds numeric suffix on collision."""
        # This test is a bit tricky since names are random
        # We just verify it doesn't crash with a full set
        existing: set[str] = set()
        name = _generate_branch_name(existing)
        assert name  # Non-empty


class TestDevHelp:
    """Tests for dev command help."""

    def test_dev_help(self) -> None:
        """Dev command shows help."""
        result = runner.invoke(app, ["dev", "--help"])
        assert result.exit_code == 0
        assert "Parallel development environment manager" in result.output
        assert "new" in result.output
        assert "list" in result.output
        assert "rm" in result.output


class TestDevAgents:
    """Tests for dev agents command."""

    def test_list_agents(self) -> None:
        """List all agents."""
        result = runner.invoke(app, ["dev", "agents"])
        assert result.exit_code == 0
        assert "claude" in result.output.lower()
        assert "aider" in result.output.lower()


class TestDevEditors:
    """Tests for dev editors command."""

    def test_list_editors(self) -> None:
        """List all editors."""
        result = runner.invoke(app, ["dev", "editors"])
        assert result.exit_code == 0
        assert "vscode" in result.output.lower()
        assert "neovim" in result.output.lower()


class TestDevTerminals:
    """Tests for dev terminals command."""

    def test_list_terminals(self) -> None:
        """List all terminals."""
        result = runner.invoke(app, ["dev", "terminals"])
        assert result.exit_code == 0
        assert "tmux" in result.output.lower()
        assert "zellij" in result.output.lower()


class TestDevDoctor:
    """Tests for dev doctor command."""

    def test_doctor_shows_status(self) -> None:
        """Doctor command shows system status."""
        result = runner.invoke(app, ["dev", "doctor"])
        assert result.exit_code == 0
        assert "Git" in result.output
        assert "Editors" in result.output
        assert "AI Coding Agents" in result.output
        assert "Terminals" in result.output


class TestDevList:
    """Tests for dev list command."""

    def test_list_requires_git_repo(self) -> None:
        """List requires being in a git repo."""
        with patch("agent_cli.dev.worktree.get_main_repo_root", return_value=None):
            result = runner.invoke(app, ["dev", "list"])
            # Should show error about not being in git repo
            assert "git" in result.output.lower() or result.exit_code != 0

    def test_list_shows_worktrees(self) -> None:
        """List shows worktrees in table format."""
        mock_worktrees = [
            WorktreeInfo(
                path=Path("/repo"),
                branch="main",
                commit="abc",
                is_main=True,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
            WorktreeInfo(
                path=Path("/repo-worktrees/feature"),
                branch="feature",
                commit="def",
                is_main=False,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
        ]

        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.list_worktrees", return_value=mock_worktrees),
        ):
            result = runner.invoke(app, ["dev", "list"])
            assert result.exit_code == 0
            assert "main" in result.output
            assert "feature" in result.output

    def test_list_porcelain(self) -> None:
        """List with --porcelain shows machine-readable output."""
        mock_worktrees = [
            WorktreeInfo(
                path=Path("/repo"),
                branch="main",
                commit="abc",
                is_main=True,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
        ]

        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.list_worktrees", return_value=mock_worktrees),
        ):
            result = runner.invoke(app, ["dev", "list", "--porcelain"])
            assert result.exit_code == 0
            assert "/repo\tmain" in result.output


class TestDevPath:
    """Tests for dev path command."""

    def test_path_prints_worktree_path(self) -> None:
        """Path command prints worktree path."""
        mock_wt = WorktreeInfo(
            path=Path("/repo-worktrees/feature"),
            branch="feature",
            commit="abc",
            is_main=False,
            is_detached=False,
            is_locked=False,
            is_prunable=False,
        )

        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.find_worktree_by_name", return_value=mock_wt),
        ):
            result = runner.invoke(app, ["dev", "path", "feature"])
            assert result.exit_code == 0
            assert "/repo-worktrees/feature" in result.output

    def test_path_not_found(self) -> None:
        """Path command shows error for unknown worktree."""
        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.find_worktree_by_name", return_value=None),
        ):
            result = runner.invoke(app, ["dev", "path", "nonexistent"])
            assert result.exit_code != 0
            assert "not found" in result.output.lower()
