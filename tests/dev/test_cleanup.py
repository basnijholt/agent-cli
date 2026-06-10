"""Tests for multiplexer-aware worktree cleanup helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from agent_cli.dev.cleanup import remove_worktree, remove_worktrees
from agent_cli.dev.terminals.tmux import TmuxCleanupResult, TmuxWindow
from agent_cli.dev.terminals.zellij import ZellijCleanupResult, ZellijTab
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

    def test_remove_worktree_cleans_multiplexers_after_git_removal(self) -> None:
        """Git removal should happen before tmux windows and zellij tabs are cleaned."""
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

        def fake_close(_path: Path) -> ZellijCleanupResult:
            call_order.append("zellij")
            return ZellijCleanupResult(
                closed_tabs=(ZellijTab(tab_id=2, session_name="shared", tab_name="agent"),),
            )

        with (
            patch("agent_cli.dev.cleanup.worktree.remove_worktree", side_effect=fake_remove),
            patch("agent_cli.dev.cleanup.Tmux") as mock_tmux_cls,
            patch("agent_cli.dev.cleanup.Zellij") as mock_zellij_cls,
        ):
            mock_tmux_cls.return_value.kill_windows_for_worktree.side_effect = fake_kill
            mock_zellij_cls.return_value.close_tabs_for_worktree.side_effect = fake_close
            result = remove_worktree(wt, Path("/repo"), force=True, delete_branch=True)

        assert result.success is True
        assert call_order == ["git", "tmux", "zellij"]

    def test_remove_worktree_surfaces_multiplexer_cleanup_errors_as_warnings(self) -> None:
        """Multiplexer cleanup failures should not fail an already-removed worktree."""
        wt = _worktree_info()

        with (
            patch("agent_cli.dev.cleanup.worktree.remove_worktree", return_value=(True, None)),
            patch("agent_cli.dev.cleanup.Tmux") as mock_tmux_cls,
            patch("agent_cli.dev.cleanup.Zellij") as mock_zellij_cls,
        ):
            mock_tmux_cls.return_value.kill_windows_for_worktree.return_value = TmuxCleanupResult(
                errors=("Failed to kill tmux window @2 in session shared: boom",),
            )
            mock_zellij_cls.return_value.close_tabs_for_worktree.return_value = ZellijCleanupResult(
                errors=("Failed to close zellij tab 2 in session shared: boom",),
            )
            result = remove_worktree(wt, Path("/repo"))

        assert result.success is True
        assert result.warnings == [
            "Failed to kill tmux window @2 in session shared: boom",
            "Failed to close zellij tab 2 in session shared: boom",
        ]

    def test_remove_worktree_skips_multiplexer_cleanup_when_git_removal_fails(self) -> None:
        """Multiplexer cleanup should not run if git worktree removal fails."""
        wt = _worktree_info()

        with (
            patch(
                "agent_cli.dev.cleanup.worktree.remove_worktree",
                return_value=(False, "cannot remove"),
            ),
            patch("agent_cli.dev.cleanup.Tmux") as mock_tmux_cls,
            patch("agent_cli.dev.cleanup.Zellij") as mock_zellij_cls,
        ):
            result = remove_worktree(wt, Path("/repo"))

        assert result.success is False
        assert result.error == "cannot remove"
        mock_tmux_cls.return_value.kill_windows_for_worktree.assert_not_called()
        mock_zellij_cls.return_value.close_tabs_for_worktree.assert_not_called()

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
