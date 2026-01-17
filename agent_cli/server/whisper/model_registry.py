"""Registry for managing multiple Whisper models."""

from __future__ import annotations

from dataclasses import dataclass

from agent_cli.server.base_model_registry import BaseModelRegistry, BaseModelStatus
from agent_cli.server.whisper.model_manager import ModelConfig, WhisperModelManager


@dataclass
class ModelStatus(BaseModelStatus):
    """Status of a registered Whisper model."""

    total_transcription_seconds: float


class WhisperModelRegistry(
    BaseModelRegistry[WhisperModelManager, ModelConfig, ModelStatus],
):
    """Registry for managing multiple Whisper models with independent TTLs.

    Each model can have its own configuration (device, compute type, TTL).
    Models are loaded lazily and unloaded independently based on their TTL.
    """

    def _create_manager(self, config: ModelConfig) -> WhisperModelManager:
        """Create a WhisperModelManager from config."""
        return WhisperModelManager(config)

    def _get_model_name(self, config: ModelConfig) -> str:
        """Get the model name from config."""
        return config.model_name

    def _get_manager_status(
        self,
        name: str,
        manager: WhisperModelManager,
    ) -> ModelStatus:
        """Get status from a manager."""
        return ModelStatus(
            name=name,
            loaded=manager.is_loaded,
            device=manager.device,
            ttl_seconds=manager.config.ttl_seconds,
            ttl_remaining=manager.ttl_remaining,
            active_requests=manager.active_requests,
            load_count=manager.stats.load_count,
            unload_count=manager.stats.unload_count,
            total_requests=manager.stats.total_requests,
            total_audio_seconds=manager.stats.total_audio_seconds,
            total_transcription_seconds=manager.stats.total_transcription_seconds,
            last_load_time=manager.stats.last_load_time,
            last_request_time=manager.stats.last_request_time,
            load_duration_seconds=manager.stats.load_duration_seconds,
        )
