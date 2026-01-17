"""TTS backend factory with platform auto-detection."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from agent_cli.server.tts.backends.base import TTSBackend

from agent_cli.server.tts.backends.base import (
    BackendConfig,
    SynthesisResult,
)

logger = logging.getLogger(__name__)

BackendType = Literal["piper", "auto"]


def detect_backend() -> Literal["piper"]:
    """Detect the best backend for the current platform.

    Returns:
        "piper" as the default backend (CPU-friendly ONNX-based TTS).

    """
    return "piper"


def create_backend(
    config: BackendConfig,
    backend_type: BackendType = "auto",
) -> TTSBackend:
    """Create a TTS backend instance.

    Args:
        config: Backend configuration.
        backend_type: Backend to use, or "auto" for platform detection.

    Returns:
        Configured TTSBackend instance.

    Raises:
        ImportError: If the required backend package is not installed.
        ValueError: If an unknown backend type is specified.

    """
    if backend_type == "auto":
        backend_type = detect_backend()

    logger.debug("Creating %s backend for model %s", backend_type, config.model_name)

    if backend_type == "piper":
        from agent_cli.server.tts.backends.piper import PiperBackend  # noqa: PLC0415

        return PiperBackend(config)

    msg = f"Unknown backend type: {backend_type}"
    raise ValueError(msg)


__all__ = [
    "BackendConfig",
    "BackendType",
    "SynthesisResult",
    "create_backend",
    "detect_backend",
]
