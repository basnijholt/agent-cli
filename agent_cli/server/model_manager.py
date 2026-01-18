"""Model manager with TTL-based unloading.

This module provides a concrete model manager that handles:
- Lazy loading of models on first request
- TTL-based automatic unloading when idle
- Active request tracking to prevent unload during processing
- Concurrent request coordination

The manager works with any backend that implements the BackendProtocol.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for a model."""

    model_name: str
    device: str = "auto"
    ttl_seconds: int = 300
    cache_dir: Path | None = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.ttl_seconds < 1:
            msg = f"ttl_seconds must be >= 1, got {self.ttl_seconds}"
            raise ValueError(msg)


@dataclass
class ModelStats:
    """Runtime statistics for a model."""

    load_count: int = 0
    unload_count: int = 0
    total_requests: int = 0
    total_audio_seconds: float = 0.0
    total_processing_seconds: float = 0.0
    last_load_time: float | None = None
    last_request_time: float | None = None
    load_duration_seconds: float | None = None
    extra: dict[str, float] = field(default_factory=dict)


@runtime_checkable
class BackendProtocol(Protocol):
    """Protocol for model backends."""

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        ...

    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on."""
        ...

    async def load(self) -> float:
        """Load the model, return load duration in seconds."""
        ...

    async def unload(self) -> None:
        """Unload the model."""
        ...


class ModelManager:
    """Manages a model with TTL-based unloading.

    The model is loaded lazily on first request and unloaded after
    being idle for longer than the configured TTL.

    Usage:
        manager = ModelManager(backend, config)
        await manager.start()

        # Use request context for processing
        async with manager.request():
            result = await backend.process(...)

        await manager.stop()
    """

    def __init__(
        self,
        backend: BackendProtocol,
        config: ModelConfig,
        stats: ModelStats | None = None,
    ) -> None:
        """Initialize the model manager.

        Args:
            backend: The backend instance to manage.
            config: Model configuration.
            stats: Optional stats instance (creates new one if not provided).

        """
        self.backend = backend
        self.config = config
        self.stats = stats or ModelStats()
        self._condition = asyncio.Condition()
        self._active_requests = 0
        self._unloading = False
        self._unload_task: asyncio.Task[None] | None = None
        self._shutdown = False

    @property
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        return self.backend.is_loaded

    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on."""
        return self.backend.device

    @property
    def active_requests(self) -> int:
        """Get the number of active requests."""
        return self._active_requests

    @property
    def ttl_remaining(self) -> float | None:
        """Get seconds remaining before model unloads, or None if not loaded."""
        if not self.is_loaded or self.stats.last_request_time is None:
            return None
        elapsed = time.time() - self.stats.last_request_time
        remaining = self.config.ttl_seconds - elapsed
        return max(0.0, remaining)

    async def start(self) -> None:
        """Start the TTL unload watcher."""
        if self._unload_task is None:
            self._unload_task = asyncio.create_task(self._unload_watcher())

    async def stop(self) -> None:
        """Stop the manager and unload the model."""
        self._shutdown = True
        if self._unload_task is not None:
            self._unload_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._unload_task
            self._unload_task = None
        await self.unload()

    async def get_model(self) -> Any:
        """Get the backend, loading it if necessary."""
        await self._ensure_loaded()
        return self.backend

    @asynccontextmanager
    async def request(self) -> AsyncIterator[None]:
        """Context manager for processing requests.

        Ensures the model is loaded and tracks active requests.
        Use this around any backend operations.

        Example:
            async with manager.request():
                result = await manager.backend.synthesize(text)

        """
        await self._begin_request()
        try:
            yield
        finally:
            await self._end_request()

    async def unload(self) -> bool:
        """Unload the model from memory.

        Returns True if model was unloaded, False if it wasn't loaded.
        """
        async with self._condition:
            while self._unloading:
                await self._condition.wait()

            if not self.backend.is_loaded:
                return False

            self._unloading = True
            try:
                while self._active_requests > 0:
                    logger.info(
                        "Waiting for %d active requests before unloading %s",
                        self._active_requests,
                        self.config.model_name,
                    )
                    await self._condition.wait()

                if not self.backend.is_loaded:
                    return False

                await self.backend.unload()
                self.stats.unload_count += 1
                return True
            finally:
                self._unloading = False
                self._condition.notify_all()

    async def _load_if_needed_locked(self) -> None:
        """Load the model if needed (expects condition lock held)."""
        if not self.backend.is_loaded:
            load_duration = await self.backend.load()
            self.stats.load_count += 1
            self.stats.last_load_time = time.time()
            self.stats.load_duration_seconds = load_duration
        self.stats.last_request_time = time.time()

    async def _ensure_loaded(self) -> None:
        """Ensure the model is loaded."""
        async with self._condition:
            while self._unloading:
                await self._condition.wait()
            await self._load_if_needed_locked()

    async def _begin_request(self) -> None:
        """Begin a request, waiting if unload is in progress."""
        async with self._condition:
            while self._unloading:
                await self._condition.wait()
            await self._load_if_needed_locked()
            self._active_requests += 1

    async def _end_request(self) -> None:
        """End a request and notify waiters if no more active requests."""
        async with self._condition:
            self._active_requests -= 1
            self.stats.last_request_time = time.time()
            if self._active_requests == 0:
                self._condition.notify_all()

    async def _unload_watcher(self) -> None:
        """Background task that unloads model after TTL expires."""
        check_interval = min(30, self.config.ttl_seconds / 2)

        while not self._shutdown:
            try:
                await asyncio.sleep(check_interval)

                async with self._condition:
                    if self._unloading:
                        continue
                    if not self.backend.is_loaded:
                        continue

                    if self.stats.last_request_time is None:
                        continue

                    idle_time = time.time() - self.stats.last_request_time

                    if idle_time >= self.config.ttl_seconds:
                        if self._active_requests == 0:
                            logger.info(
                                "Model %s idle for %.0fs (ttl=%ds), unloading",
                                self.config.model_name,
                                idle_time,
                                self.config.ttl_seconds,
                            )
                            await self.backend.unload()
                            self.stats.unload_count += 1
                        else:
                            logger.debug(
                                "Model %s would unload but has %d active requests",
                                self.config.model_name,
                                self._active_requests,
                            )

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in unload watcher")
