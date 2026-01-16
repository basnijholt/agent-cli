"""TTS model manager with TTL-based unloading."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_cli.server.base_model_manager import (
    BaseModelConfig,
    BaseModelManager,
    BaseModelStats,
)
from agent_cli.server.tts.backends import (
    BackendConfig,
    BackendType,
    SynthesisResult,
    create_backend,
)

if TYPE_CHECKING:
    from agent_cli.server.tts.backends.base import TTSBackend

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig(BaseModelConfig):
    """Configuration for a TTS model."""

    voice: str | None = None
    backend_type: BackendType = "auto"


@dataclass
class ModelStats(BaseModelStats):
    """Runtime statistics for a TTS model."""

    total_characters: int = 0
    total_synthesis_seconds: float = 0.0


class TTSModelManager(BaseModelManager["TTSBackend", ModelConfig, ModelStats]):
    """Manages a TTS model with TTL-based unloading.

    The model is loaded lazily on first request and unloaded after
    being idle for longer than the configured TTL.

    Delegates actual synthesis to a backend (piper, etc.).
    """

    def _create_backend(self) -> TTSBackend:
        """Create the TTS backend."""
        return create_backend(
            BackendConfig(
                model_name=self._config.model_name,
                voice=self._config.voice,
                device=self._config.device,
                cache_dir=self._config.cache_dir,
            ),
            backend_type=self._config.backend_type,
        )

    def _create_stats(self) -> ModelStats:
        """Create the stats instance."""
        return ModelStats()

    @property
    def _backend_is_loaded(self) -> bool:
        """Check if the backend is loaded."""
        return self._backend.is_loaded

    @property
    def _backend_device(self) -> str | None:
        """Get the backend's device."""
        return self._backend.device

    async def _backend_load(self) -> float:
        """Load the backend, return load duration in seconds."""
        return await self._backend.load()

    async def _backend_unload(self) -> None:
        """Unload the backend."""
        await self._backend.unload()

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
        await self._begin_request()

        start_time = time.time()

        try:
            result = await self._backend.synthesize(
                text,
                voice=voice,
                speed=speed,
            )

            synthesis_duration = time.time() - start_time

            # Update stats
            self._stats.total_requests += 1
            self._stats.total_characters += len(text)
            self._stats.total_audio_seconds += result.duration
            self._stats.total_synthesis_seconds += synthesis_duration

            logger.debug(
                "Synthesized %d chars to %.1fs audio in %.2fs (model=%s)",
                len(text),
                result.duration,
                synthesis_duration,
                self._config.model_name,
            )

            return result

        finally:
            await self._end_request()
