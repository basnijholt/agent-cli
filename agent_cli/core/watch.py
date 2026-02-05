"""Shared watchfiles helper."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from watchfiles import Change


def _default_skip_hidden(path: Path, root: Path) -> bool:
    """Default filter that skips hidden files and directories."""
    rel_parts = path.relative_to(root).parts
    return any(part.startswith(".") for part in rel_parts)


async def watch_directory(
    root: Path,
    handler: Callable[[Change, Path], None],
    *,
    skip_hidden: bool = True,
    ignore_filter: Callable[[Path, Path], bool] | None = None,
    use_executor: bool = True,
) -> None:
    """Watch a directory for file changes and invoke handler(change, path).

    Args:
        root: The directory to watch.
        handler: Callback invoked with (change_type, path) for each file change.
        skip_hidden: If True, skip files/dirs starting with '.'. Ignored if
            ignore_filter is provided.
        ignore_filter: Optional custom filter function(path, root) -> bool.
            Returns True if the path should be ignored. Overrides skip_hidden.
        use_executor: If True, run handler in a thread pool executor.

    """
    from watchfiles import awatch  # noqa: PLC0415

    loop = asyncio.get_running_loop()

    # Determine which filter to use
    if ignore_filter is not None:
        should_skip = ignore_filter
    elif skip_hidden:
        should_skip = _default_skip_hidden
    else:
        should_skip = None

    async for changes in awatch(root):
        for change_type, file_path_str in changes:
            path = Path(file_path_str)
            if path.is_dir():
                continue

            if should_skip is not None and should_skip(path, root):
                continue

            if use_executor:
                await loop.run_in_executor(None, handler, change_type, path)
            else:
                handler(change_type, path)
