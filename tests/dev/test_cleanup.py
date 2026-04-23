"""Tests for tmux-aware worktree cleanup helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from agent_cli.dev.cleanup import remove_worktree, remove_worktrees
from agent_cli.dev.terminals.tmux import TmuxCleanupResult, TmuxWindow
from agent_cli.dev.worktree import WorktreeInfo


def _worktree_info() -> WorktreeInfo:
    return WorktreeInfo(
        path=Path("/repo-worktrees/feature"),
        branch="feature",
        commit="abc",
        is_main=False,
        is_detached=False,
        is_locked=False,
        is_prunable=False,
    )


class TestCleanup:
    """Tests for shared worktree cleanup orchestration."""

    def test_remove_worktree_cleans_tmux_after_git_removal(self) -> None:
        """Git removal should happen before tagged tmux windows are killed."""
        wt = _worktree_info()
        call_order: list[str] = []

        def fake_remove(*_args: object, **_kwargs: object) -> tuple[bool, str | None]:
            call_order.append("git")
            return True, None

        def fake_kill(_path: Path) -> TmuxCleanupResult:
            call_order.append("tmux")
            return TmuxCleanupResult(
                killed_windows=(
                    TmuxWindow(window_id="@2", session_name="shared", window_name="agent"),
                ),
            )

        with (
            patch("agent_cli.dev.cleanup.worktree.remove_worktree", side_effect=fake_remove),
            patch("agent_cli.dev.cleanup.Tmux") as mock_tmux_cls,
        ):
            mock_tmux_cls.return_value.kill_windows_for_worktree.side_effect = fake_kill
            result = remove_worktree(wt, Path("/repo"), force=True, delete_branch=True)

        assert result.success is True
        assert call_order == ["git", "tmux"]

    def test_remove_worktree_surfaces_tmux_cleanup_errors_as_warnings(self) -> None:
        """Tmux cleanup failures should not fail an already-removed worktree."""
        wt = _worktree_info()

        with (
            patch("agent_cli.dev.cleanup.worktree.remove_worktree", return_value=(True, None)),
            patch("agent_cli.dev.cleanup.Tmux") as mock_tmux_cls,
        ):
            mock_tmux_cls.return_value.kill_windows_for_worktree.return_value = TmuxCleanupResult(
                errors=("Failed to kill tmux window @2 in session shared: boom",),
            )
            result = remove_worktree(wt, Path("/repo"))

        assert result.success is True
        assert result.warnings == ["Failed to kill tmux window @2 in session shared: boom"]

    def test_remove_worktree_skips_tmux_cleanup_when_git_removal_fails(self) -> None:
        """Tmux cleanup should not run if git worktree removal fails."""
        wt = _worktree_info()

        with (
            patch(
                "agent_cli.dev.cleanup.worktree.remove_worktree",
                return_value=(False, "cannot remove"),
            ),
            patch("agent_cli.dev.cleanup.Tmux") as mock_tmux_cls,
        ):
            result = remove_worktree(wt, Path("/repo"))

        assert result.success is False
        assert result.error == "cannot remove"
        mock_tmux_cls.return_value.kill_windows_for_worktree.assert_not_called()

    def test_remove_worktrees_deletes_branches_for_cleanups(self) -> None:
        """Batch cleanups should request branch deletion for each worktree."""
        wt = _worktree_info()

        with patch("agent_cli.dev.cleanup.remove_worktree") as mock_remove:
            remove_worktrees([wt], Path("/repo"), force=True)

        mock_remove.assert_called_once_with(
            wt,
            Path("/repo"),
            force=True,
            delete_branch=True,
        )
