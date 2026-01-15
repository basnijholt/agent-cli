"""Whisper backend factory with platform auto-detection."""

from __future__ import annotations

import logging
import platform
import sys
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from agent_cli.server.whisper.backends.base import WhisperBackend

from agent_cli.server.whisper.backends.base import (
    BackendConfig,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)

BackendType = Literal["faster-whisper", "mlx", "auto"]


def detect_backend() -> Literal["faster-whisper", "mlx"]:
    """Detect the best backend for the current platform.

    Returns:
        "mlx" on macOS ARM with mlx-whisper installed,
        "faster-whisper" otherwise.

    """
    # Check for macOS ARM (Apple Silicon)
    if sys.platform == "darwin" and platform.machine() == "arm64":
        try:
            import mlx_whisper  # noqa: F401, PLC0415

            logger.debug("Detected macOS ARM with mlx-whisper available")
            return "mlx"
        except ImportError:
            logger.debug("macOS ARM detected but mlx-whisper not installed")

    return "faster-whisper"


def create_backend(
    config: BackendConfig,
    backend_type: BackendType = "auto",
) -> WhisperBackend:
    """Create a Whisper backend instance.

    Args:
        config: Backend configuration.
        backend_type: Backend to use, or "auto" for platform detection.

    Returns:
        Configured WhisperBackend instance.

    Raises:
        ImportError: If the required backend package is not installed.
        ValueError: If an unknown backend type is specified.

    """
    if backend_type == "auto":
        backend_type = detect_backend()

    logger.debug("Creating %s backend for model %s", backend_type, config.model_name)

    if backend_type == "mlx":
        from agent_cli.server.whisper.backends.mlx import MLXWhisperBackend  # noqa: PLC0415

        return MLXWhisperBackend(config)

    if backend_type == "faster-whisper":
        from agent_cli.server.whisper.backends.faster_whisper import (  # noqa: PLC0415
            FasterWhisperBackend,
        )

        return FasterWhisperBackend(config)

    msg = f"Unknown backend type: {backend_type}"
    raise ValueError(msg)


__all__ = [
    "BackendConfig",
    "BackendType",
    "TranscriptionResult",
    "create_backend",
    "detect_backend",
]
