"""Faster-whisper backend for Linux/CUDA systems."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager, get_context
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from agent_cli.core.process import set_process_title
from agent_cli.server.streaming import AsyncQueueReader, QueueWriter
from agent_cli.server.whisper.backends.base import (
    BackendConfig,
    TranscriptionResult,
    TranscriptionSegment,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


# --- Subprocess worker functions (run in isolated process) ---


def _load_model_in_subprocess(
    model_name: str,
    device: str,
    compute_type: str,
    cpu_threads: int,
    download_root: str | None,
) -> str:
    """Load model in subprocess. Returns actual device string."""
    from faster_whisper import WhisperModel  # noqa: PLC0415

    set_process_title("whisper-faster")
    model = WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        download_root=download_root,
    )
    return str(model.model.device)


def _transcribe_in_subprocess(
    model_name: str,
    device: str,
    compute_type: str,
    cpu_threads: int,
    download_root: str | None,
    audio_bytes: bytes,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Run transcription in subprocess. Model is loaded fresh each call."""
    from faster_whisper import WhisperModel  # noqa: PLC0415

    model = WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        download_root=download_root,
    )

    # Write audio to temp file - faster-whisper needs a file path
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, info = model.transcribe(tmp_path, **kwargs)
        segment_list = list(segments)  # Consume lazy generator
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {
        "text": " ".join(seg.text.strip() for seg in segment_list),
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "segments": [
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
    }


def _transcribe_stream_in_subprocess(
    model_name: str,
    device: str,
    compute_type: str,
    cpu_threads: int,
    download_root: str | None,
    audio_bytes: bytes,
    kwargs: dict[str, Any],
    output_queue: Any,
) -> None:
    """Stream transcription segments through queue as they are processed."""
    from faster_whisper import WhisperModel  # noqa: PLC0415

    writer = QueueWriter(output_queue)

    try:
        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
            download_root=download_root,
        )

        # Write audio to temp file - faster-whisper needs a file path
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            segments, info = model.transcribe(tmp_path, **kwargs)

            # Iterate over lazy generator and send each segment as it's ready
            segment_count = 0
            for seg in segments:
                writer.send_data(
                    seg.text.encode("utf-8"),
                    {
                        "segment_id": seg.id,
                        "start": seg.start,
                        "end": seg.end,
                        "language": info.language,
                        "language_probability": info.language_probability,
                    },
                )
                segment_count += 1

            writer.send_done(
                {
                    "segment_count": segment_count,
                    "language": info.language,
                    "language_probability": info.language_probability,
                    "duration": info.duration,
                },
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    except Exception as e:
        writer.send_error(e)


class FasterWhisperBackend:
    """Whisper backend using faster-whisper (CTranslate2).

    Uses subprocess isolation: when unloaded, the subprocess terminates
    and the OS reclaims ALL memory (Python's pymalloc doesn't return
    freed memory to OS otherwise).
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the backend."""
        self._config = config
        self._executor: ProcessPoolExecutor | None = None
        self._device: str | None = None

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._executor is not None

    @property
    def device(self) -> str | None:
        """Get the device the model is on."""
        return self._device

    async def load(self) -> float:
        """Start subprocess and load model."""
        import time  # noqa: PLC0415

        logger.debug(
            "Starting faster-whisper subprocess for model %s (device=%s, compute_type=%s)",
            self._config.model_name,
            self._config.device,
            self._config.compute_type,
        )

        start_time = time.time()

        # Subprocess isolation: spawn context for clean state
        ctx = get_context("spawn")
        self._executor = ProcessPoolExecutor(max_workers=1, mp_context=ctx)

        download_root = str(self._config.cache_dir) if self._config.cache_dir else None
        loop = asyncio.get_running_loop()
        self._device = await loop.run_in_executor(
            self._executor,
            _load_model_in_subprocess,
            self._config.model_name,
            self._config.device,
            self._config.compute_type,
            self._config.cpu_threads,
            download_root,
        )

        load_duration = time.time() - start_time
        logger.info(
            "Model %s loaded on %s in %.2fs",
            self._config.model_name,
            self._device,
            load_duration,
        )
        return load_duration

    async def unload(self) -> None:
        """Shutdown subprocess, releasing ALL memory."""
        if self._executor is None:
            return
        logger.debug(
            "Shutting down faster-whisper subprocess for model %s",
            self._config.model_name,
        )
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._executor = None
        self._device = None
        logger.info("Model %s unloaded (subprocess terminated)", self._config.model_name)

    async def transcribe(
        self,
        audio: bytes,
        *,
        source_filename: str | None = None,  # noqa: ARG002
        language: str | None = None,
        task: Literal["transcribe", "translate"] = "transcribe",
        initial_prompt: str | None = None,
        temperature: float = 0.0,
        vad_filter: bool = True,
        word_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio using faster-whisper in subprocess."""
        if self._executor is None:
            msg = "Model not loaded. Call load() first."
            raise RuntimeError(msg)

        kwargs: dict[str, Any] = {
            "language": language,
            "task": task,
            "initial_prompt": initial_prompt,
            "temperature": temperature,
            "vad_filter": vad_filter,
            "word_timestamps": word_timestamps,
        }

        download_root = str(self._config.cache_dir) if self._config.cache_dir else None
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            self._executor,
            _transcribe_in_subprocess,
            self._config.model_name,
            self._config.device,
            self._config.compute_type,
            self._config.cpu_threads,
            download_root,
            audio,
            kwargs,
        )

        return TranscriptionResult(
            text=result["text"],
            language=result["language"],
            language_probability=result["language_probability"],
            duration=result["duration"],
            segments=result["segments"],
        )

    @property
    def supports_streaming(self) -> bool:
        """Faster-whisper backend supports streaming transcription."""
        return True

    async def transcribe_stream(
        self,
        audio: bytes,
        *,
        source_filename: str | None = None,  # noqa: ARG002
        language: str | None = None,
        task: Literal["transcribe", "translate"] = "transcribe",
        initial_prompt: str | None = None,
        temperature: float = 0.0,
        vad_filter: bool = True,
    ) -> AsyncIterator[TranscriptionSegment]:
        """Stream transcription segments as they are processed."""
        if self._executor is None:
            msg = "Model not loaded. Call load() first."
            raise RuntimeError(msg)

        kwargs: dict[str, Any] = {
            "language": language,
            "task": task,
            "initial_prompt": initial_prompt,
            "temperature": temperature,
            "vad_filter": vad_filter,
        }

        download_root = str(self._config.cache_dir) if self._config.cache_dir else None

        # Use Manager queue for cross-process communication
        manager = Manager()
        try:
            queue = manager.Queue(maxsize=10)  # Backpressure control
            loop = asyncio.get_running_loop()

            # Submit streaming worker to subprocess
            future = loop.run_in_executor(
                self._executor,
                _transcribe_stream_in_subprocess,
                self._config.model_name,
                self._config.device,
                self._config.compute_type,
                self._config.cpu_threads,
                download_root,
                audio,
                kwargs,
                queue,  # type: ignore[arg-type]
            )

            # Yield segments as they arrive
            reader = AsyncQueueReader(queue, timeout=60.0)  # type: ignore[arg-type]
            async for chunk in reader:
                if chunk.chunk_type == "done":
                    break
                if chunk.chunk_type == "error":
                    msg = str(chunk.payload)
                    raise RuntimeError(msg)
                if chunk.payload is not None and chunk.metadata is not None:
                    yield TranscriptionSegment(
                        text=chunk.payload.decode("utf-8")
                        if isinstance(chunk.payload, bytes)
                        else str(chunk.payload),
                        start=chunk.metadata["start"],
                        end=chunk.metadata["end"],
                        segment_id=chunk.metadata["segment_id"],
                    )

            # Ensure subprocess completes
            await future
        finally:
            manager.shutdown()
