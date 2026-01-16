"""Registry for managing multiple TTS models."""

from __future__ import annotations

from dataclasses import dataclass

from agent_cli.server.base_model_registry import BaseModelRegistry, BaseModelStatus
from agent_cli.server.tts.model_manager import ModelConfig, TTSModelManager


@dataclass
class ModelStatus(BaseModelStatus):
    """Status of a registered TTS model."""

    total_characters: int
    total_synthesis_seconds: float


class TTSModelRegistry(
    BaseModelRegistry[TTSModelManager, ModelConfig, ModelStatus],
):
    """Registry for managing multiple TTS models with independent TTLs.

    Each model can have its own configuration (device, TTL).
    Models are loaded lazily and unloaded independently based on their TTL.
    """

    def _create_manager(self, config: ModelConfig) -> TTSModelManager:
        """Create a TTSModelManager from config."""
        return TTSModelManager(config)

    def _get_model_name(self, config: ModelConfig) -> str:
        """Get the model name from config."""
        return config.model_name

    def _get_manager_status(
        self,
        name: str,
        manager: TTSModelManager,
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
            total_characters=manager.stats.total_characters,
            total_synthesis_seconds=manager.stats.total_synthesis_seconds,
            last_load_time=manager.stats.last_load_time,
            last_request_time=manager.stats.last_request_time,
            load_duration_seconds=manager.stats.load_duration_seconds,
        )

    async def _start_manager(self, manager: TTSModelManager) -> None:
        """Start a manager."""
        await manager.start()

    async def _stop_manager(self, manager: TTSModelManager) -> None:
        """Stop a manager."""
        await manager.stop()

    async def _preload_manager(self, manager: TTSModelManager) -> None:
        """Preload a manager's model."""
        await manager.get_model()

    def _is_manager_loaded(self, manager: TTSModelManager) -> bool:
        """Check if a manager's model is loaded."""
        return manager.is_loaded
