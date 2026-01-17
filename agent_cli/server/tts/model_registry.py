"""Registry for managing multiple TTS models."""

from __future__ import annotations

from dataclasses import dataclass

from agent_cli.server.model_registry import ModelRegistry, ModelStatus
from agent_cli.server.tts.model_manager import TTSModelConfig, TTSModelManager


@dataclass
class TTSModelStatus(ModelStatus):
    """Status of a registered TTS model."""

    total_characters: int
    total_synthesis_seconds: float


def _get_tts_status(name: str, manager: TTSModelManager) -> TTSModelStatus:
    """Get status from a TTS manager."""
    return TTSModelStatus(
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
        total_processing_seconds=manager.stats.total_processing_seconds,
        total_characters=int(manager.stats.extra.get("total_characters", 0)),
        total_synthesis_seconds=manager.stats.extra.get("total_synthesis_seconds", 0.0),
        last_load_time=manager.stats.last_load_time,
        last_request_time=manager.stats.last_request_time,
        load_duration_seconds=manager.stats.load_duration_seconds,
        extra=manager.stats.extra,
    )


def create_tts_registry(
    default_model: str | None = None,
) -> ModelRegistry[TTSModelManager, TTSModelConfig]:
    """Create a TTS model registry.

    Args:
        default_model: Name of the default model to use when not specified.

    Returns:
        Configured ModelRegistry for TTS models.

    """
    return ModelRegistry(
        manager_factory=TTSModelManager,
        get_model_name=lambda c: c.model_name,
        get_status=_get_tts_status,
        default_model=default_model,
    )


# Alias for backward compatibility
TTSModelRegistry = ModelRegistry[TTSModelManager, TTSModelConfig]
