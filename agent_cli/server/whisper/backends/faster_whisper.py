"""Faster-whisper backend for Linux/CUDA systems."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from agent_cli.server.whisper.backends.base import (
    BackendConfig,
    TranscriptionResult,
    release_memory,
)

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


class FasterWhisperBackend:
    """Whisper backend using faster-whisper (CTranslate2).

    Best for Linux with CUDA or CPU inference.
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the backend."""
        self._config = config
        self._model: WhisperModel | None = None

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None

    @property
    def device(self) -> str | None:
        """Get the device the model is on."""
        if self._model is None:
            return None
        return str(self._model.model.device)

    async def load(self) -> float:
        """Load the faster-whisper model."""
        import time  # noqa: PLC0415

        from faster_whisper import WhisperModel  # noqa: PLC0415

        logger.info(
            "Loading faster-whisper model %s (device=%s, compute_type=%s)",
            self._config.model_name,
            self._config.device,
            self._config.compute_type,
        )

        start_time = time.time()

        self._model = await asyncio.to_thread(
            WhisperModel,
            self._config.model_name,
            device=self._config.device,
            compute_type=self._config.compute_type,
            cpu_threads=self._config.cpu_threads,
            download_root=str(self._config.cache_dir) if self._config.cache_dir else None,
        )

        load_duration = time.time() - start_time

        assert self._model is not None  # for type checker
        logger.info(
            "Loaded faster-whisper model %s on %s in %.2fs",
            self._config.model_name,
            self._model.model.device,
            load_duration,
        )

        return load_duration

    async def unload(self) -> None:
        """Unload the model and free memory."""
        if self._model is None:
            return

        logger.info("Unloading faster-whisper model %s", self._config.model_name)

        del self._model
        self._model = None

        release_memory()

        logger.info("Unloaded faster-whisper model %s", self._config.model_name)

    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str | None = None,
        task: Literal["transcribe", "translate"] = "transcribe",
        initial_prompt: str | None = None,
        temperature: float = 0.0,
        vad_filter: bool = True,
        word_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio using faster-whisper."""
        if self._model is None:
            msg = "Model not loaded. Call load() first."
            raise RuntimeError(msg)

        # Write audio to temp file - faster-whisper needs a file path
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio)
            tmp_path = tmp.name

        try:
            segments, info = await asyncio.to_thread(
                self._model.transcribe,
                tmp_path,
                language=language,
                task=task,
                initial_prompt=initial_prompt,
                temperature=temperature,
                vad_filter=vad_filter,
                word_timestamps=word_timestamps,
            )
            # Consume the lazy generator before deleting file
            segment_list = list(segments)
        finally:
            with contextlib.suppress(OSError):
                Path(tmp_path).unlink()

        text = " ".join(seg.text.strip() for seg in segment_list)

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
