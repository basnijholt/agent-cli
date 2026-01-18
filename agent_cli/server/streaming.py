"""Core streaming types for subprocess-based audio generation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from multiprocessing import Queue


@dataclass
class StreamChunk:
    """A chunk of streamed data from a subprocess worker."""

    chunk_type: Literal["data", "error", "done"]
    payload: bytes | str | None = None
    metadata: dict[str, Any] | None = None


class AsyncQueueReader:
    """Async iterator over multiprocessing.Queue with timeout handling."""

    def __init__(self, queue: Queue, *, timeout: float = 30.0) -> None:
        """Initialize reader with queue and timeout."""
        self._queue = queue
        self._timeout = timeout

    def __aiter__(self) -> AsyncIterator[StreamChunk]:
        """Return async iterator."""
        return self

    async def __anext__(self) -> StreamChunk:
        """Get the next chunk from the queue."""
        loop = asyncio.get_running_loop()
        try:
            chunk = await asyncio.wait_for(
                loop.run_in_executor(None, self._queue.get),
                timeout=self._timeout,
            )
        except TimeoutError as e:
            msg = f"Queue read timeout after {self._timeout}s"
            raise TimeoutError(msg) from e
        return chunk


class QueueWriter:
    """Helper for subprocess to send chunks/errors/done sentinel."""

    def __init__(self, queue: Queue) -> None:
        """Initialize writer with queue."""
        self._queue = queue

    def send_data(self, data: bytes, metadata: dict[str, Any] | None = None) -> None:
        """Send a data chunk."""
        self._queue.put(StreamChunk("data", data, metadata))

    def send_error(self, error: str | Exception) -> None:
        """Send an error chunk."""
        error_msg = str(error) if isinstance(error, Exception) else error
        self._queue.put(StreamChunk("error", error_msg))

    def send_done(self, metadata: dict[str, Any] | None = None) -> None:
        """Send the done sentinel."""
        self._queue.put(StreamChunk("done", metadata=metadata))
