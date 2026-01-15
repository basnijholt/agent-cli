"""Registry for managing multiple Whisper models."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agent_cli.server.whisper.model_manager import ModelConfig, WhisperModelManager

logger = logging.getLogger(__name__)


@dataclass
class ModelStatus:
    """Status of a registered model."""

    name: str
    loaded: bool
    device: str | None
    ttl_seconds: int
    ttl_remaining: float | None
    total_requests: int
    active_requests: int


class WhisperModelRegistry:
    """Registry for managing multiple Whisper models with independent TTLs.

    Each model can have its own configuration (device, compute type, TTL).
    Models are loaded lazily and unloaded independently based on their TTL.
    """

    def __init__(self, default_model: str | None = None) -> None:
        """Initialize the registry.

        Args:
            default_model: Name of the default model to use when not specified.

        """
        self._managers: dict[str, WhisperModelManager] = {}
        self._default_model = default_model
        self._started = False

    @property
    def default_model(self) -> str | None:
        """Get the default model name."""
        return self._default_model

    @default_model.setter
    def default_model(self, name: str | None) -> None:
        """Set the default model name."""
        if name is not None and name not in self._managers:
            msg = f"Model '{name}' is not registered"
            raise ValueError(msg)
        self._default_model = name

    @property
    def models(self) -> list[str]:
        """Get list of registered model names."""
        return list(self._managers.keys())

    def register(self, config: ModelConfig) -> None:
        """Register a model with the given configuration.

        Args:
            config: Model configuration including name, device, TTL, etc.

        Raises:
            ValueError: If a model with this name is already registered.

        """
        if config.model_name in self._managers:
            msg = f"Model '{config.model_name}' is already registered"
            raise ValueError(msg)

        manager = WhisperModelManager(config)
        self._managers[config.model_name] = manager

        # Set as default if it's the first model
        if self._default_model is None:
            self._default_model = config.model_name

        logger.debug(
            "Registered model %s (device=%s, ttl=%ds)",
            config.model_name,
            config.device,
            config.ttl_seconds,
        )

    def get_manager(self, model_name: str | None = None) -> WhisperModelManager:
        """Get the manager for a specific model.

        Args:
            model_name: Name of the model, or None to use the default.

        Returns:
            The WhisperModelManager for the requested model.

        Raises:
            ValueError: If the model is not registered or no default is set.

        """
        name = model_name or self._default_model

        if name is None:
            msg = "No model specified and no default model set"
            raise ValueError(msg)

        if name not in self._managers:
            msg = f"Model '{name}' is not registered. Available: {list(self._managers.keys())}"
            raise ValueError(msg)

        return self._managers[name]

    def list_status(self) -> list[ModelStatus]:
        """Get status of all registered models."""
        return [
            ModelStatus(
                name=name,
                loaded=manager.is_loaded,
                device=manager.device,
                ttl_seconds=manager.config.ttl_seconds,
                ttl_remaining=manager.ttl_remaining,
                total_requests=manager.stats.total_requests,
                active_requests=manager.active_requests,
            )
            for name, manager in self._managers.items()
        ]

    async def start(self) -> None:
        """Start all model managers (TTL watchers)."""
        if self._started:
            return

        for manager in self._managers.values():
            await manager.start()

        self._started = True
        logger.debug("Started registry with %d model(s)", len(self._managers))

    async def stop(self) -> None:
        """Stop all model managers and unload all models."""
        for manager in self._managers.values():
            await manager.stop()

        self._started = False
        logger.debug("Stopped registry")

    async def preload(self, model_names: list[str] | None = None) -> None:
        """Preload models into memory.

        Args:
            model_names: List of model names to preload, or None for all.

        """
        names = model_names or list(self._managers.keys())

        for name in names:
            if name not in self._managers:
                logger.warning("Cannot preload unknown model: %s", name)
                continue

            manager = self._managers[name]
            if not manager.is_loaded:
                logger.debug("Preloading model %s", name)
                await manager.get_model()
