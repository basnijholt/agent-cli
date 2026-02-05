"""Registry for managing multiple wakeword models."""

from __future__ import annotations

from agent_cli.server.model_registry import ModelRegistry
from agent_cli.server.wakeword.model_manager import WakewordModelConfig, WakewordModelManager


def create_wakeword_registry(
    default_model: str | None = None,
) -> ModelRegistry[WakewordModelManager, WakewordModelConfig]:
    """Create a wakeword model registry.

    Args:
        default_model: Name of the default model to use when not specified.

    Returns:
        Configured ModelRegistry for wakeword models.

    """
    return ModelRegistry(
        manager_factory=WakewordModelManager,
        default_model=default_model,
    )


# Alias for type hints
WakewordModelRegistry = ModelRegistry[WakewordModelManager, WakewordModelConfig]
