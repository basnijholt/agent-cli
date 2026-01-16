"""Base types and protocol for Whisper backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path


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
