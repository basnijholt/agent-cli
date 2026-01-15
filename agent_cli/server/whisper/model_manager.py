"""Whisper model manager with TTL-based unloading."""

from __future__ import annotations

import asyncio
import contextlib
import gc
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from faster_whisper import WhisperModel

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


@dataclass
class TranscriptionResult:
    """Result of a transcription."""

    text: str
    language: str
    language_probability: float
    duration: float
    segments: list[dict[str, Any]] = field(default_factory=list)


class WhisperModelManager:
    """Manages a single Whisper model with TTL-based unloading.

    The model is loaded lazily on first request and unloaded after
    being idle for longer than the configured TTL.
    """

    def __init__(self, config: ModelConfig) -> None:
        """Initialize the model manager."""
        self._config = config
        self._model: WhisperModel | None = None
        self._lock = asyncio.Lock()
        self._active_requests = 0
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
        return self._model is not None

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
        if self._model is None:
            return None
        return str(self._model.model.device)

    async def start(self) -> None:
        """Start the TTL unload watcher."""
        if self._unload_task is None:
            self._unload_task = asyncio.create_task(self._unload_watcher())
            logger.info(
                "Started TTL watcher for model %s (ttl=%ds)",
                self._config.model_name,
                self._config.ttl_seconds,
            )

    async def stop(self) -> None:
        """Stop the manager and unload the model."""
        self._shutdown = True
        if self._unload_task is not None:
            self._unload_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._unload_task
            self._unload_task = None
        await self.unload()

    async def get_model(self) -> WhisperModel:
        """Get the model, loading it if necessary."""
        async with self._lock:
            if self._model is None:
                await self._load_model()
            self._stats.last_request_time = time.time()
            assert self._model is not None
            return self._model

    async def _load_model(self) -> None:
        """Load the model into memory."""
        from faster_whisper import WhisperModel  # noqa: PLC0415

        logger.info(
            "Loading Whisper model %s (device=%s, compute_type=%s)",
            self._config.model_name,
            self._config.device,
            self._config.compute_type,
        )

        start_time = time.time()

        # Run model loading in thread pool to avoid blocking
        self._model = await asyncio.to_thread(
            WhisperModel,
            self._config.model_name,
            device=self._config.device,
            compute_type=self._config.compute_type,
            cpu_threads=self._config.cpu_threads,
            download_root=str(self._config.cache_dir) if self._config.cache_dir else None,
        )

        load_duration = time.time() - start_time
        self._stats.load_count += 1
        self._stats.last_load_time = time.time()
        self._stats.last_request_time = time.time()
        self._stats.load_duration_seconds = load_duration

        assert self._model is not None  # For type checker
        logger.info(
            "Loaded model %s on %s in %.2fs",
            self._config.model_name,
            self._model.model.device,
            load_duration,
        )

    async def unload(self) -> bool:
        """Unload the model from memory.

        Returns True if model was unloaded, False if it wasn't loaded.
        """
        # First check if model is loaded (with lock)
        async with self._lock:
            if self._model is None:
                return False

        # Wait for active requests without holding lock to avoid deadlock
        # (transcribe() needs lock to decrement _active_requests)
        while self._active_requests > 0:
            logger.info(
                "Waiting for %d active requests before unloading %s",
                self._active_requests,
                self._config.model_name,
            )
            await asyncio.sleep(0.5)

        # Re-acquire lock and unload
        async with self._lock:
            # Re-check in case model was unloaded by another task
            if self._model is None:
                return False
            return await self._do_unload()

    async def _do_unload(self) -> bool:
        """Actually unload the model. Must be called with lock held."""
        if self._model is None:
            return False

        logger.info("Unloading model %s", self._config.model_name)

        del self._model
        self._model = None

        # Force memory release
        gc.collect()

        # Try to release CUDA memory if available
        try:
            import torch  # noqa: PLC0415

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("Released CUDA memory")
        except ImportError:
            pass

        self._stats.unload_count += 1
        logger.info("Unloaded model %s", self._config.model_name)
        return True

    async def _unload_watcher(self) -> None:
        """Background task that unloads model after TTL expires."""
        check_interval = min(30, self._config.ttl_seconds / 2)

        while not self._shutdown:
            try:
                await asyncio.sleep(check_interval)

                async with self._lock:
                    if self._model is None:
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
                            await self._do_unload()
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
        language: str | None = None,
        task: str = "transcribe",
        initial_prompt: str | None = None,
        temperature: float = 0.0,
        vad_filter: bool = True,
        word_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio data.

        Args:
            audio: Audio data as bytes (WAV format preferred)
            language: Language code (e.g., "en") or None for auto-detection
            task: "transcribe" or "translate"
            initial_prompt: Optional prompt to guide transcription
            temperature: Sampling temperature
            vad_filter: Whether to use VAD filtering
            word_timestamps: Whether to include word-level timestamps

        Returns:
            TranscriptionResult with text and metadata

        """
        import io  # noqa: PLC0415

        model = await self.get_model()

        async with self._lock:
            self._active_requests += 1

        start_time = time.time()

        try:
            # Run transcription in thread pool
            segments, info = await asyncio.to_thread(
                model.transcribe,
                io.BytesIO(audio),
                language=language,
                task=task,
                initial_prompt=initial_prompt,
                temperature=temperature,
                vad_filter=vad_filter,
                word_timestamps=word_timestamps,
            )

            # Consume the generator
            segment_list = list(segments)
            text = " ".join(seg.text.strip() for seg in segment_list)

            transcription_duration = time.time() - start_time

            # Update stats
            self._stats.total_requests += 1
            self._stats.total_audio_seconds += info.duration
            self._stats.total_transcription_seconds += transcription_duration
            self._stats.last_request_time = time.time()

            logger.debug(
                "Transcribed %.1fs audio in %.2fs (model=%s, lang=%s)",
                info.duration,
                transcription_duration,
                self._config.model_name,
                info.language,
            )

            return TranscriptionResult(
                text=text,
                language=info.language,
                language_probability=info.language_probability,
                duration=info.duration,
                segments=[
                    {
                        "id": seg.id,
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg.text,
                        "tokens": seg.tokens,
                        "avg_logprob": seg.avg_logprob,
                        "no_speech_prob": seg.no_speech_prob,
                    }
                    for seg in segment_list
                ],
            )

        finally:
            async with self._lock:
                self._active_requests -= 1
                self._stats.last_request_time = time.time()
