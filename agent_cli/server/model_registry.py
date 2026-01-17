"""Registry for managing multiple models.

This module provides a concrete model registry that handles:
- Registration of multiple models with independent configurations
- Default model selection
- Lifecycle management (start/stop)
- Model preloading
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


@runtime_checkable
class ManagerProtocol(Protocol):
    """Protocol defining the interface for model managers."""

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        ...

    async def start(self) -> None:
        """Start the manager."""
        ...

    async def stop(self) -> None:
        """Stop the manager."""
        ...

    async def get_model(self) -> Any:
        """Get the model, loading if needed."""
        ...


# Type variable for manager type
ManagerT = TypeVar("ManagerT", bound=ManagerProtocol)
ConfigT = TypeVar("ConfigT")


@dataclass
class ModelStatus:
    """Status of a registered model."""

    name: str
    loaded: bool
    device: str | None
    ttl_seconds: int
    ttl_remaining: float | None
    active_requests: int
    # Stats
    load_count: int
    unload_count: int
    total_requests: int
    total_audio_seconds: float
    total_processing_seconds: float
    last_load_time: float | None
    last_request_time: float | None
    load_duration_seconds: float | None
    extra: dict[str, float]


class ModelRegistry(Generic[ManagerT, ConfigT]):
    """Registry for managing multiple models with independent TTLs.

    Each model can have its own configuration (device, TTL).
    Models are loaded lazily and unloaded independently based on their TTL.
    """

    def __init__(
        self,
        manager_factory: Callable[[ConfigT], ManagerT],
        default_model: str | None = None,
    ) -> None:
        """Initialize the registry.

        Args:
            manager_factory: Function to create a manager from config.
            default_model: Name of the default model to use when not specified.

        """
        self._manager_factory = manager_factory
        self._managers: dict[str, ManagerT] = {}
        self._default_model = default_model
        self._started = False

    @staticmethod
    def _default_get_status(name: str, manager: Any) -> ModelStatus:
        """Default status getter for managers with standard interface."""
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
            total_processing_seconds=manager.stats.total_processing_seconds,
            last_load_time=manager.stats.last_load_time,
            last_request_time=manager.stats.last_request_time,
            load_duration_seconds=manager.stats.load_duration_seconds,
            extra=manager.stats.extra,
        )

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

    def register(self, config: ConfigT) -> None:
        """Register a model with the given configuration.

        Args:
            config: Model configuration including name, device, TTL, etc.
                Must have a model_name attribute.

        Raises:
            ValueError: If a model with this name is already registered.

        """
        model_name: str = config.model_name  # type: ignore[attr-defined]

        if model_name in self._managers:
            msg = f"Model '{model_name}' is already registered"
            raise ValueError(msg)

        manager = self._manager_factory(config)
        self._managers[model_name] = manager

        # Set as default if it's the first model
        if self._default_model is None:
            self._default_model = model_name

        logger.debug("Registered model %s", model_name)

    def get_manager(self, model_name: str | None = None) -> ManagerT:
        """Get the manager for a specific model.

        Args:
            model_name: Name of the model, or None to use the default.

        Returns:
            The manager for the requested model.

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
        return [self._default_get_status(name, manager) for name, manager in self._managers.items()]

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
