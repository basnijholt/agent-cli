"""Base types and protocol for TTS backends."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def get_torch_device() -> str:
    """Detect the best available PyTorch device."""
    try:
        import torch  # noqa: PLC0415

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def has_gpu() -> bool:
    """Check if a GPU (CUDA or MPS) is available."""
    return get_torch_device() in ("cuda", "mps")


def get_backend_cache_dir(backend_name: str) -> Path:
    """Get default cache directory for a TTS backend."""
    cache_dir = Path.home() / ".cache" / backend_name
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@dataclass
class SynthesisResult:
    """Result of a synthesis operation."""

    audio: bytes
    sample_rate: int
    sample_width: int
    channels: int
    duration: float


@dataclass
class BackendConfig:
    """Configuration for a TTS backend."""

    model_name: str
    device: str = "auto"
    cache_dir: Path | None = None


class InvalidTextError(ValueError):
    """Raised when the input text is invalid or unsupported."""


@runtime_checkable
class TTSBackend(Protocol):
    """Protocol for TTS synthesis backends.

    Backends handle model loading, unloading, and synthesis.
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
            voice: Voice to use (optional, uses model default if not specified).
            speed: Speech speed multiplier (0.25 to 4.0).

        Returns:
            SynthesisResult with audio data and metadata.

        """
        ...

    @property
    def supports_streaming(self) -> bool:
        """Check if backend supports streaming synthesis."""
        return False

    def synthesize_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> AsyncIterator[bytes]:
        """Stream synthesized audio chunks as they are generated.

        Implementations should be async generators (async def with yield).

        Args:
            text: Text to synthesize.
            voice: Voice to use (optional).
            speed: Speech speed multiplier (0.25 to 4.0).

        Yields:
            Raw PCM audio chunks (int16, mono).

        """
        ...
