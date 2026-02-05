"""Base types and protocol for wakeword backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003 - Path needed at runtime for dataclass fields
from typing import Protocol, runtime_checkable


@dataclass
class DetectionResult:
    """Result of a wake word detection."""

    name: str
    timestamp: int  # milliseconds into the audio stream
    probability: float


@dataclass
class BackendConfig:
    """Configuration for a wakeword backend."""

    model_name: str
    device: str = "cpu"  # Wakeword detection is typically CPU-based
    cache_dir: Path | None = None
    threshold: float = 0.5
    trigger_level: int = 1
    refractory_seconds: float = 2.0
    custom_model_dir: Path | None = None


@dataclass
class ModelInfo:
    """Information about an available wake word model."""

    name: str
    phrase: str
    languages: list[str] = field(default_factory=lambda: ["en"])
    is_builtin: bool = True


@runtime_checkable
class WakewordBackend(Protocol):
    """Protocol for wakeword detection backends.

    Backends handle model loading, unloading, and detection.
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

    def reset(self) -> None:
        """Reset the detector state for a new audio stream."""
        ...

    def process_audio(self, audio_chunk: bytes) -> list[DetectionResult]:
        """Process an audio chunk and return any detections.

        Args:
            audio_chunk: Raw PCM audio bytes (16-bit, 16kHz, mono).

        Returns:
            List of detections found in this chunk.

        """
        ...

    def get_available_models(self) -> list[ModelInfo]:
        """Get list of available wake word models."""
        ...
