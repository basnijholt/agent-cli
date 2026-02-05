"""Wakeword backend implementations."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from typing import Literal

from agent_cli.server.wakeword.backends.base import (
    BackendConfig,
    DetectionResult,
    WakewordBackend,
)


def _has(package: str) -> bool:
    return find_spec(package) is not None


BackendType = Literal["openwakeword"]


@dataclass
class WakewordBackendConfig(BackendConfig):
    """Extended configuration for wakeword backends."""

    threshold: float = 0.5
    trigger_level: int = 1
    refractory_seconds: float = 2.0


def detect_backend() -> BackendType:
    """Detect the best available wakeword backend."""
    if _has("pyopen_wakeword"):
        return "openwakeword"

    msg = "No wakeword backend available. Install pyopen-wakeword: pip install pyopen-wakeword"
    raise RuntimeError(msg)


def create_backend(
    config: WakewordBackendConfig,
    backend_type: BackendType = "openwakeword",
) -> WakewordBackend:
    """Create a wakeword backend instance.

    Args:
        config: Backend configuration.
        backend_type: Type of backend to create.

    Returns:
        A WakewordBackend instance.

    """
    if backend_type == "openwakeword":
        from agent_cli.server.wakeword.backends.openwakeword import (  # noqa: PLC0415
            OpenWakeWordBackend,
        )

        return OpenWakeWordBackend(config)

    msg = f"Unknown backend type: {backend_type}"
    raise ValueError(msg)


__all__ = [
    "BackendConfig",
    "BackendType",
    "DetectionResult",
    "WakewordBackend",
    "WakewordBackendConfig",
    "create_backend",
    "detect_backend",
]
