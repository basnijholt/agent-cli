"""Tests for shared watch helper."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from watchfiles import Change

from agent_cli.core import watch as watch_mod

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_watch_directory_skips_hidden(tmp_path: Path) -> None:
    """Only non-hidden files trigger the handler."""
    called: list[tuple[Change, Path]] = []

    async def fake_awatch(_root: Path) -> Any:  # type: ignore[override]
        yield {
            (Change.added, str(tmp_path / "visible.txt")),
            (Change.added, str(tmp_path / ".hidden.txt")),
            (Change.added, str(tmp_path / "sub/.nested")),
            (Change.deleted, str(tmp_path / "gone.txt")),
        }

    def handler(change: Change, path: Path) -> None:
        called.append((change, path))

    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "visible.txt").touch()
    (tmp_path / "gone.txt").touch()
    (tmp_path / "sub").mkdir()

    # Patch awatch used inside watch_directory
    original = watch_mod.awatch
    watch_mod.awatch = fake_awatch  # type: ignore[assignment]
    try:
        await watch_mod.watch_directory(tmp_path, handler)
    finally:
        watch_mod.awatch = original  # type: ignore[assignment]

    seen_paths = {p.name for _, p in called}
    assert "visible.txt" in seen_paths
    assert "gone.txt" in seen_paths
    assert ".hidden.txt" not in seen_paths
    assert ".nested" not in seen_paths
