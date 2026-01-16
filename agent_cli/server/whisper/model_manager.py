"""Whisper model manager with TTL-based unloading."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from agent_cli.server.base_model_manager import (
    BaseModelConfig,
    BaseModelManager,
    BaseModelStats,
)
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
class ModelConfig(BaseModelConfig):
    """Configuration for a Whisper model."""

    compute_type: str = "auto"
    cpu_threads: int = 4
    backend_type: BackendType = "auto"


@dataclass
class ModelStats(BaseModelStats):
    """Runtime statistics for a Whisper model."""

    total_transcription_seconds: float = 0.0


class WhisperModelManager(BaseModelManager["WhisperBackend", ModelConfig, ModelStats]):
    """Manages a Whisper model with TTL-based unloading.

    The model is loaded lazily on first request and unloaded after
    being idle for longer than the configured TTL.

    Delegates actual transcription to a backend (faster-whisper or mlx).
    """

    def _create_backend(self) -> WhisperBackend:
        """Create the Whisper backend."""
        return create_backend(
            BackendConfig(
                model_name=self._config.model_name,
                device=self._config.device,
                compute_type=self._config.compute_type,
                cpu_threads=self._config.cpu_threads,
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

            logger.debug(
                "Transcribed %.1fs audio in %.2fs (model=%s, lang=%s)",
                result.duration,
                transcription_duration,
                self._config.model_name,
                result.language,
            )

            return result

        finally:
            await self._end_request()
