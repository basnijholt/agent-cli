"""Registry for managing multiple TTS models."""

from __future__ import annotations

from agent_cli.server.model_registry import ModelRegistry
from agent_cli.server.tts.model_manager import TTSModelConfig, TTSModelManager


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
        default_model=default_model,
    )


# Alias for type hints
TTSModelRegistry = ModelRegistry[TTSModelManager, TTSModelConfig]
