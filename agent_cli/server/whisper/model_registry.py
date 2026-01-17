"""Registry for managing multiple Whisper models."""

from __future__ import annotations

from agent_cli.server.model_registry import ModelRegistry
from agent_cli.server.whisper.model_manager import WhisperModelConfig, WhisperModelManager


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
        default_model=default_model,
    )


# Alias for type hints
WhisperModelRegistry = ModelRegistry[WhisperModelManager, WhisperModelConfig]
