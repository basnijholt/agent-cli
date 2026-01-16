"""Base types and protocol for Whisper backends."""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from multiprocessing import get_context
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

T = TypeVar("T")


@dataclass
class TranscriptionResult:
    """Result of a transcription."""

    text: str
    language: str
    language_probability: float
    duration: float
    segments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BackendConfig:
    """Configuration for a Whisper backend."""

    model_name: str
    device: str = "auto"
    compute_type: str = "auto"
    cpu_threads: int = 4
    cache_dir: Path | None = None


class InvalidAudioError(ValueError):
    """Raised when the input audio is invalid or unsupported."""


class SubprocessExecutor:
    """Manages a subprocess pool for isolated model execution.

    Uses ProcessPoolExecutor with a single worker in spawn mode.
    When stopped, the subprocess terminates and the OS reclaims ALL memory
    (Python's pymalloc doesn't return freed memory to OS otherwise).
    """

    __slots__ = ("_executor",)

    def __init__(self) -> None:
        """Initialize the executor in stopped state."""
        self._executor: ProcessPoolExecutor | None = None

    @property
    def is_running(self) -> bool:
        """Check if the subprocess is running."""
        return self._executor is not None

    def start(self) -> None:
        """Start the subprocess worker."""
        if self._executor is not None:
            return
        ctx = get_context("spawn")
        self._executor = ProcessPoolExecutor(max_workers=1, mp_context=ctx)

    def stop(self) -> None:
        """Stop the subprocess worker, releasing all memory."""
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

    async def run(self, fn: Callable[..., T], *args: Any) -> T:
        """Run a function in the subprocess.

        Args:
            fn: A picklable function to run in the subprocess.
            *args: Arguments to pass to the function (must be picklable).

        Returns:
            The function's return value.

        Raises:
            RuntimeError: If the subprocess is not running.

        """
        if self._executor is None:
            msg = "Subprocess not started. Call start() first."
            raise RuntimeError(msg)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn, *args)


@runtime_checkable
class WhisperBackend(Protocol):
    """Protocol for Whisper transcription backends.

    Backends handle model loading, unloading, and transcription.
    The ModelManager handles TTL, stats, and lifecycle.
    """

    @property
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        ...

    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on, or None if not loaded."""
        ...

    async def load(self) -> float:
        """Load the model into memory.

        Returns:
            Load duration in seconds.

        """
        ...

    async def unload(self) -> None:
        """Unload the model and free memory."""
        ...

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
            audio: Audio data as bytes (WAV format, 16kHz, 16-bit, mono)
            source_filename: Optional filename to help detect audio format.
            language: Language code or None for auto-detection
            task: "transcribe" or "translate" (to English)
            initial_prompt: Optional prompt to guide transcription
            temperature: Sampling temperature
            vad_filter: Whether to use VAD filtering
            word_timestamps: Whether to include word-level timestamps

        Returns:
            TranscriptionResult with text and metadata.

        """
        ...
