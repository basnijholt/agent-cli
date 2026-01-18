"""TTS model manager with TTL-based unloading."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_cli import constants
from agent_cli.server.model_manager import ModelConfig, ModelManager, ModelStats
from agent_cli.server.tts.backends import (
    BackendConfig,
    BackendType,
    SynthesisResult,
    create_backend,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from agent_cli.server.tts.backends.base import TTSBackend

logger = logging.getLogger(__name__)


@dataclass
class TTSModelConfig(ModelConfig):
    """Configuration for a TTS model."""

    backend_type: BackendType = "auto"


class TTSModelManager:
    """Manages a TTS model with TTL-based unloading.

    Thin wrapper around ModelManager that adds the synthesize() method.
    """

    def __init__(self, config: TTSModelConfig) -> None:
        """Initialize the TTS model manager."""
        self.config = config
        backend = create_backend(
            BackendConfig(
                model_name=config.model_name,
                device=config.device,
                cache_dir=config.cache_dir,
            ),
            backend_type=config.backend_type,
        )
        self._manager = ModelManager(backend, config)

    @property
    def stats(self) -> ModelStats:
        """Get the model statistics."""
        return self._manager.stats

    @property
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        return self._manager.is_loaded

    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on."""
        return self._manager.device

    @property
    def active_requests(self) -> int:
        """Get the number of active requests."""
        return self._manager.active_requests

    @property
    def ttl_remaining(self) -> float | None:
        """Get seconds remaining before model unloads."""
        return self._manager.ttl_remaining

    async def start(self) -> None:
        """Start the TTL unload watcher."""
        await self._manager.start()

    async def stop(self) -> None:
        """Stop the manager and unload the model."""
        await self._manager.stop()

    async def get_model(self) -> TTSBackend:
        """Get the backend, loading it if necessary."""
        return await self._manager.get_model()

    async def unload(self) -> bool:
        """Unload the model from memory."""
        return await self._manager.unload()

    def _update_stats(self, text: str, synthesis_duration: float) -> None:
        """Update synthesis statistics."""
        stats = self._manager.stats
        stats.total_requests += 1
        stats.total_processing_seconds += synthesis_duration
        stats.extra["total_characters"] = stats.extra.get("total_characters", 0.0) + len(text)
        stats.extra["total_synthesis_seconds"] = (
            stats.extra.get("total_synthesis_seconds", 0.0) + synthesis_duration
        )

    async def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> SynthesisResult:
        """Synthesize text to audio.

        Args:
            text: Text to synthesize.
            voice: Voice to use (optional).
            speed: Speech speed multiplier (0.25 to 4.0).

        Returns:
            SynthesisResult with audio data and metadata.

        """
        start_time = time.time()

        async with self._manager.request():
            backend: TTSBackend = self._manager.backend  # type: ignore[assignment]
            result = await backend.synthesize(
                text,
                voice=voice,
                speed=speed,
            )

        synthesis_duration = time.time() - start_time

        self._update_stats(text, synthesis_duration)
        self._manager.stats.total_audio_seconds += result.duration

        logger.debug(
            "Synthesized %d chars to %.1fs audio in %.2fs (model=%s)",
            len(text),
            result.duration,
            synthesis_duration,
            self.config.model_name,
        )

        return result

    @property
    def supports_streaming(self) -> bool:
        """Check if the backend supports streaming synthesis."""
        backend: TTSBackend = self._manager.backend  # type: ignore[assignment]
        return backend.supports_streaming

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> AsyncIterator[bytes]:
        """Stream synthesized audio chunks as they are generated."""
        start_time = time.time()
        chunk_count = 0
        total_bytes = 0

        async with self._manager.request():
            backend: TTSBackend = self._manager.backend  # type: ignore[assignment]

            if not backend.supports_streaming:
                msg = "Backend does not support streaming"
                raise RuntimeError(msg)

            async for chunk in backend.synthesize_stream(
                text,
                voice=voice,
                speed=speed,
            ):
                chunk_count += 1
                total_bytes += len(chunk)
                yield chunk

        synthesis_duration = time.time() - start_time

        # Calculate audio duration from PCM bytes (16-bit mono)
        bytes_per_second = constants.KOKORO_DEFAULT_SAMPLE_RATE * 2  # 2 bytes per sample
        audio_seconds = total_bytes / bytes_per_second

        self._update_stats(text, synthesis_duration)
        self._manager.stats.total_audio_seconds += audio_seconds
        self._manager.stats.extra["streaming_requests"] = (
            self._manager.stats.extra.get("streaming_requests", 0) + 1
        )

        logger.debug(
            "Streamed %d chars to %.1fs audio in %d chunks (%d bytes) in %.2fs (model=%s)",
            len(text),
            audio_seconds,
            chunk_count,
            total_bytes,
            synthesis_duration,
            self.config.model_name,
        )
