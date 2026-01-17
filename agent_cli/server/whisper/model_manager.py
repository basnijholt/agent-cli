"""Whisper model manager with TTL-based unloading."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from agent_cli.server.model_manager import ModelConfig, ModelManager, ModelStats
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
class WhisperModelConfig(ModelConfig):
    """Configuration for a Whisper model."""

    compute_type: str = "auto"
    cpu_threads: int = 4
    backend_type: BackendType = "auto"


class WhisperModelManager:
    """Manages a Whisper model with TTL-based unloading.

    Thin wrapper around ModelManager that adds the transcribe() method.
    """

    def __init__(self, config: WhisperModelConfig) -> None:
        """Initialize the Whisper model manager."""
        self.config = config
        backend = create_backend(
            BackendConfig(
                model_name=config.model_name,
                device=config.device,
                compute_type=config.compute_type,
                cpu_threads=config.cpu_threads,
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

    async def get_model(self) -> WhisperBackend:
        """Get the backend, loading it if necessary."""
        return await self._manager.get_model()

    async def unload(self) -> bool:
        """Unload the model from memory."""
        return await self._manager.unload()

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
        start_time = time.time()

        async with self._manager.request():
            backend: WhisperBackend = self._manager.backend  # type: ignore[assignment]
            result = await backend.transcribe(
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
        stats = self._manager.stats
        stats.total_requests += 1
        stats.total_audio_seconds += result.duration
        stats.total_processing_seconds += transcription_duration
        stats.extra["total_transcription_seconds"] = (
            stats.extra.get("total_transcription_seconds", 0.0) + transcription_duration
        )

        logger.debug(
            "Transcribed %.1fs audio in %.2fs (model=%s, lang=%s)",
            result.duration,
            transcription_duration,
            self.config.model_name,
            result.language,
        )

        return result
