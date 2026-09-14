"""Base types and protocol for Whisper backends."""

from __future__ import annotations

import io
import logging
import wave
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from agent_cli.core.audio_format import convert_audio_to_wav_format

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Result of a transcription."""

    text: str
    language: str
    language_probability: float
    duration: float
    segments: list[dict[str, Any]] = field(default_factory=list)
    supports_segments: bool = True


@dataclass
class BackendConfig:
    """Configuration for a Whisper backend."""

    model_name: str
    device: str = "auto"
    compute_type: str = "auto"
    cpu_threads: int = 4
    cache_dir: Path | None = None
    default_language: str | None = None
    trust_remote_code: bool = False
    max_new_tokens: int = 4096


class InvalidAudioError(ValueError):
    """Raised when the input audio is invalid or unsupported."""


class UnsupportedRequestError(ValueError):
    """Raised when the backend cannot satisfy the requested transcription behavior."""


def ensure_wav_container(
    audio: bytes,
    source_filename: str | None,
    *,
    backend_label: str,
) -> bytes:
    """Return a WAV container for backends that hand a file path to a WAV-only parser.

    Uploads that already parse as WAV are returned untouched; anything else is
    transcoded with FFmpeg, using ``source_filename`` as the demuxer hint. Call this
    on the async side before dispatching to a model subprocess.
    """
    try:
        with wave.open(io.BytesIO(audio), "rb"):
            return audio
    except (wave.Error, EOFError):
        pass

    filename = source_filename or "audio"
    try:
        return convert_audio_to_wav_format(audio, filename)
    except RuntimeError as exc:
        logger.warning("FFmpeg conversion failed for %s: %s", backend_label, exc)
        msg = (
            f"Unsupported audio format for {backend_label}. "
            "Provide a WAV file or install ffmpeg to convert uploads."
        )
        raise InvalidAudioError(msg) from exc


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
