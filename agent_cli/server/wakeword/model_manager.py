"""Wakeword model manager with TTL-based unloading."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent_cli.server.model_manager import ModelConfig, ModelManager, ModelStats
from agent_cli.server.wakeword.backend import DetectionResult, OpenWakeWordBackend

if TYPE_CHECKING:
    from pathlib import Path

    from agent_cli.server.wakeword.backend import ModelInfo

logger = logging.getLogger(__name__)


@dataclass
class WakewordModelConfig(ModelConfig):
    """Configuration for a wakeword model."""

    threshold: float = 0.5
    trigger_level: int = 1
    refractory_seconds: float = 2.0
    custom_model_dir: Path | None = None


class WakewordModelManager:
    """Manages a wakeword model with TTL-based unloading."""

    def __init__(self, config: WakewordModelConfig) -> None:
        """Initialize the wakeword model manager."""
        self.config = config
        backend = OpenWakeWordBackend(
            model_name=config.model_name,
            threshold=config.threshold,
            trigger_level=config.trigger_level,
            refractory_seconds=config.refractory_seconds,
            custom_model_dir=config.custom_model_dir,
        )
        self._manager = ModelManager(backend, config)

    @property
    def stats(self) -> ModelStats:
        """Get the model statistics."""
        return self._manager.stats

    @property
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        return self._manager.is_loaded

    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on."""
        return self._manager.device

    @property
    def active_requests(self) -> int:
        """Get the number of active requests."""
        return self._manager.active_requests

    @property
    def ttl_remaining(self) -> float | None:
        """Get seconds remaining before model unloads."""
        return self._manager.ttl_remaining

    async def start(self) -> None:
        """Start the TTL unload watcher."""
        await self._manager.start()

    async def stop(self) -> None:
        """Stop the manager and unload the model."""
        await self._manager.stop()

    async def get_model(self) -> OpenWakeWordBackend:
        """Get the backend, loading it if necessary."""
        return await self._manager.get_model()

    async def unload(self) -> bool:
        """Unload the model from memory."""
        return await self._manager.unload()

    def reset(self) -> None:
        """Reset the detector state for a new audio stream."""
        if self._manager.is_loaded:
            backend: OpenWakeWordBackend = self._manager.backend  # type: ignore[assignment]
            backend.reset()

    async def process_audio(self, audio_chunk: bytes) -> list[DetectionResult]:
        """Process an audio chunk and return any detections."""
        async with self._manager.request():
            backend: OpenWakeWordBackend = self._manager.backend  # type: ignore[assignment]
            detections = backend.process_audio(audio_chunk)

        if detections:
            stats = self._manager.stats
            stats.total_requests += len(detections)
            stats.extra["total_detections"] = stats.extra.get("total_detections", 0.0) + len(
                detections,
            )

        return detections

    def get_available_models(self) -> list[ModelInfo]:
        """Get list of available wake word models."""
        if self._manager.is_loaded:
            backend: OpenWakeWordBackend = self._manager.backend  # type: ignore[assignment]
            return backend.get_available_models()
        return []
