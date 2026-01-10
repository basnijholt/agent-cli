"""Space - Parallel development environment manager using git worktrees.

A Python implementation inspired by git-worktree-runner (gtr), providing:
- Git worktree management with simplified commands
- Editor integration (Cursor, VS Code, Zed)
- AI coding agent integration (Claude, Codex, Gemini, Aider)
- Terminal integration (iTerm2, Kitty, Warp)
- Project type detection and automatic setup
"""

from __future__ import annotations

__all__ = ["app"]

from .cli import app
