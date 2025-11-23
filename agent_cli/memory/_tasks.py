"""Utilities for tracking background tasks in the memory proxy."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Coroutine

LOGGER = logging.getLogger(__name__)

_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _track_background(task: asyncio.Task[Any], label: str) -> asyncio.Task[Any]:
    """Track background tasks and surface failures."""
    _BACKGROUND_TASKS.add(task)

    def _done_callback(done: asyncio.Task[Any]) -> None:
        _BACKGROUND_TASKS.discard(done)
        if done.cancelled():
            LOGGER.debug("Background task %s cancelled", label)
            return
        exc = done.exception()
        if exc:
            LOGGER.exception("Background task %s failed", label, exc_info=exc)

    task.add_done_callback(_done_callback)
    return task


def run_in_background(
    coro: asyncio.Task[Any] | Coroutine[Any, Any, Any],
    label: str,
) -> asyncio.Task[Any]:
    """Create and track a background asyncio task."""
    task = coro if isinstance(coro, asyncio.Task) else asyncio.create_task(coro)
    task.set_name(f"memory-{label}")
    return _track_background(task, label)


async def wait_for_background_tasks() -> None:
    """Await any in-flight background tasks (useful in tests)."""
    while _BACKGROUND_TASKS:
        tasks = list(_BACKGROUND_TASKS)
        await asyncio.gather(*tasks, return_exceptions=False)
