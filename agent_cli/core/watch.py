"""Shared watchfiles helper."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from watchfiles import Change, awatch

ChangeHandler = Callable[[Change, Path], None]


async def watch_directory(
    root: Path,
    handler: ChangeHandler,
    *,
    skip_hidden: bool = True,
    use_executor: bool = True,
) -> None:
    """Watch a directory for file changes and invoke handler(change, path)."""
    loop = asyncio.get_running_loop()

    async for changes in awatch(root):
        for change_type, file_path_str in changes:
            path = Path(file_path_str)
            if path.is_dir():
                continue

            if skip_hidden:
                try:
                    rel_parts = path.relative_to(root).parts
                    if any(part.startswith(".") for part in rel_parts):
                        continue
                except ValueError:
                    if path.name.startswith("."):
                        continue

            if use_executor:
                await loop.run_in_executor(None, handler, change_type, path)
            else:
                handler(change_type, path)
