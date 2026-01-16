"""Whisper model manager with TTL-based unloading."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pathlib import Path

from agent_cli.server.whisper.backends import (
    BackendConfig,
    BackendType,
    TranscriptionResult,
    create_backend,
)

if TYPE_CHECKING:
    from agent_cli.server.whisper.backends.base import WhisperBackend

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for a Whisper model."""

    model_name: str
    device: str = "auto"
    compute_type: str = "auto"
    ttl_seconds: int = 300
    cache_dir: Path | None = None
    cpu_threads: int = 4
    backend_type: BackendType = "auto"

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
    total_transcription_seconds: float = 0.0
    last_load_time: float | None = None
    last_request_time: float | None = None
    load_duration_seconds: float | None = None


class WhisperModelManager:
    """Manages a Whisper model with TTL-based unloading.

    The model is loaded lazily on first request and unloaded after
    being idle for longer than the configured TTL.

    Delegates actual transcription to a backend (faster-whisper or mlx).
    """

    def __init__(self, config: ModelConfig) -> None:
        """Initialize the model manager."""
        self._config = config
        self._backend: WhisperBackend = create_backend(
            BackendConfig(
                model_name=config.model_name,
                device=config.device,
                compute_type=config.compute_type,
                cpu_threads=config.cpu_threads,
                cache_dir=config.cache_dir,
            ),
            backend_type=config.backend_type,
        )
        self._condition = asyncio.Condition()
        self._active_requests = 0
        self._unloading = False
        self._stats = ModelStats()
        self._unload_task: asyncio.Task[None] | None = None
        self._shutdown = False

    @property
    def config(self) -> ModelConfig:
        """Get the model configuration."""
        return self._config

    @property
    def stats(self) -> ModelStats:
        """Get the model statistics."""
        return self._stats

    @property
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        return self._backend.is_loaded

    def ensure_downloaded(self) -> None:
        """Download model files if not already cached, without loading into memory."""
        self._backend.ensure_downloaded()

    @property
    def ttl_remaining(self) -> float | None:
        """Get seconds remaining before model unloads, or None if not loaded."""
        if not self.is_loaded or self._stats.last_request_time is None:
            return None
        elapsed = time.time() - self._stats.last_request_time
        remaining = self._config.ttl_seconds - elapsed
        return max(0.0, remaining)

    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on."""
        return self._backend.device

    @property
    def active_requests(self) -> int:
        """Get the number of active requests."""
        return self._active_requests

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

    async def get_model(self) -> WhisperBackend:
        """Get the backend, loading it if necessary.

        Returns:
            The WhisperBackend instance.

        """
        await self._ensure_loaded()
        return self._backend

    async def _load_if_needed_locked(self) -> None:
        """Load the model if needed (expects condition lock held)."""
        if not self._backend.is_loaded:
            load_duration = await self._backend.load()
            self._stats.load_count += 1
            self._stats.last_load_time = time.time()
            self._stats.load_duration_seconds = load_duration
        self._stats.last_request_time = time.time()

    async def _ensure_loaded(self) -> None:
        """Ensure the model is loaded."""
        async with self._condition:
            while self._unloading:
                await self._condition.wait()
            await self._load_if_needed_locked()

    async def _begin_request(self) -> None:
        """Begin a transcription request, waiting if unload is in progress."""
        async with self._condition:
            while self._unloading:
                await self._condition.wait()
            await self._load_if_needed_locked()
            self._active_requests += 1

    async def unload(self) -> bool:
        """Unload the model from memory.

        Returns True if model was unloaded, False if it wasn't loaded.
        """
        async with self._condition:
            while self._unloading:
                await self._condition.wait()

            if not self._backend.is_loaded:
                return False

            self._unloading = True
            try:
                while self._active_requests > 0:
                    logger.info(
                        "Waiting for %d active requests before unloading %s",
                        self._active_requests,
                        self._config.model_name,
                    )
                    await self._condition.wait()

                if not self._backend.is_loaded:
                    return False

                await self._backend.unload()
                self._stats.unload_count += 1
                return True
            finally:
                self._unloading = False
                self._condition.notify_all()

    async def _unload_watcher(self) -> None:
        """Background task that unloads model after TTL expires."""
        check_interval = min(30, self._config.ttl_seconds / 2)

        while not self._shutdown:
            try:
                await asyncio.sleep(check_interval)

                async with self._condition:
                    if self._unloading:
                        continue
                    if not self._backend.is_loaded:
                        continue

                    if self._stats.last_request_time is None:
                        continue

                    idle_time = time.time() - self._stats.last_request_time

                    if idle_time >= self._config.ttl_seconds:
                        if self._active_requests == 0:
                            logger.info(
                                "Model %s idle for %.0fs (ttl=%ds), unloading",
                                self._config.model_name,
                                idle_time,
                                self._config.ttl_seconds,
                            )
                            await self._backend.unload()
                            self._stats.unload_count += 1
                        else:
                            logger.debug(
                                "Model %s would unload but has %d active requests",
                                self._config.model_name,
                                self._active_requests,
                            )

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in unload watcher")

    async def transcribe(
        self,
        audio: bytes,
        *,
        source_filename: str | None = None,
        language: str | None = None,
        task: Literal["transcribe", "translate"] = "transcribe",
        initial_prompt: str | None = None,
        temperature: float = 0.0,
        vad_filter: bool = True,
        word_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio data.

        Args:
            audio: Audio data as bytes (WAV format preferred)
            source_filename: Optional filename to help detect audio format.
            language: Language code (e.g., "en") or None for auto-detection
            task: "transcribe" or "translate"
            initial_prompt: Optional prompt to guide transcription
            temperature: Sampling temperature
            vad_filter: Whether to use VAD filtering
            word_timestamps: Whether to include word-level timestamps

        Returns:
            TranscriptionResult with text and metadata

        """
        await self._begin_request()

        start_time = time.time()

        try:
            result = await self._backend.transcribe(
                audio,
                source_filename=source_filename,
                language=language,
                task=task,
                initial_prompt=initial_prompt,
                temperature=temperature,
                vad_filter=vad_filter,
                word_timestamps=word_timestamps,
            )

            transcription_duration = time.time() - start_time

            # Update stats
            self._stats.total_requests += 1
            self._stats.total_audio_seconds += result.duration
            self._stats.total_transcription_seconds += transcription_duration
            self._stats.last_request_time = time.time()

            logger.debug(
                "Transcribed %.1fs audio in %.2fs (model=%s, lang=%s)",
                result.duration,
                transcription_duration,
                self._config.model_name,
                result.language,
            )

            return result

        finally:
            async with self._condition:
                self._active_requests -= 1
                self._stats.last_request_time = time.time()
                if self._active_requests == 0:
                    self._condition.notify_all()
