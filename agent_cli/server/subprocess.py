"""Subprocess executor for model isolation."""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")


class SubprocessExecutor:
    """Manages a single-worker ProcessPoolExecutor with spawn context.

    Provides subprocess isolation for ML model backends. When stopped,
    the subprocess terminates and the OS reclaims all memory.

    Usage:
        executor = SubprocessExecutor()
        executor.start()
        result = await executor.run(my_function, arg1, arg2)
        executor.stop()
    """

    def __init__(self) -> None:
        """Initialize the executor (not started)."""
        self._executor: ProcessPoolExecutor | None = None

    @property
    def is_running(self) -> bool:
        """Check if the subprocess is running."""
        return self._executor is not None

    @property
    def executor(self) -> ProcessPoolExecutor | None:
        """Get the underlying executor (for advanced use cases like streaming)."""
        return self._executor

    def start(self) -> None:
        """Start the subprocess. No-op if already running."""
        if self._executor is not None:
            return
        ctx = get_context("spawn")
        self._executor = ProcessPoolExecutor(max_workers=1, mp_context=ctx)

    def stop(self) -> None:
        """Stop the subprocess. No-op if not running."""
        if self._executor is None:
            return
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._executor = None

    async def run(self, fn: Callable[..., T], *args: Any) -> T:
        """Run a function in the subprocess.

        Args:
            fn: Function to run (must be picklable).
            *args: Arguments to pass to the function.

        Returns:
            The function's return value.

        Raises:
            RuntimeError: If the subprocess is not running.

        """
        if self._executor is None:
            msg = "Subprocess not started. Call start() first."
            raise RuntimeError(msg)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn, *args)
