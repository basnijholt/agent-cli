"""Registry for managing multiple Whisper models."""

from __future__ import annotations

from dataclasses import dataclass

from agent_cli.server.model_registry import ModelRegistry, ModelStatus
from agent_cli.server.whisper.model_manager import WhisperModelConfig, WhisperModelManager


@dataclass
class WhisperModelStatus(ModelStatus):
    """Status of a registered Whisper model."""

    total_transcription_seconds: float


def _get_whisper_status(name: str, manager: WhisperModelManager) -> WhisperModelStatus:
    """Get status from a Whisper manager."""
    return WhisperModelStatus(
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
        total_transcription_seconds=manager.stats.extra.get("total_transcription_seconds", 0.0),
        last_load_time=manager.stats.last_load_time,
        last_request_time=manager.stats.last_request_time,
        load_duration_seconds=manager.stats.load_duration_seconds,
        extra=manager.stats.extra,
    )


def create_whisper_registry(
    default_model: str | None = None,
) -> ModelRegistry[WhisperModelManager, WhisperModelConfig]:
    """Create a Whisper model registry.

    Args:
        default_model: Name of the default model to use when not specified.

    Returns:
        Configured ModelRegistry for Whisper models.

    """
    return ModelRegistry(
        manager_factory=WhisperModelManager,
        get_model_name=lambda c: c.model_name,
        get_status=_get_whisper_status,
        default_model=default_model,
    )


# Alias for backward compatibility
WhisperModelRegistry = ModelRegistry[WhisperModelManager, WhisperModelConfig]
