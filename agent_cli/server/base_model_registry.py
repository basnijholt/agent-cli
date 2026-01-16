"""Base registry for managing multiple models.

This module provides a generic base class for model registries that handle:
- Registration of multiple models with independent configurations
- Default model selection
- Lifecycle management (start/stop)
- Model preloading
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

# Type variables for generic registry
ManagerT = TypeVar("ManagerT")
ConfigT = TypeVar("ConfigT")
StatusT = TypeVar("StatusT")


@dataclass
class BaseModelStatus:
    """Base status of a registered model."""

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
    last_load_time: float | None
    last_request_time: float | None
    load_duration_seconds: float | None


class BaseModelRegistry(ABC, Generic[ManagerT, ConfigT, StatusT]):
    """Base registry for managing multiple models with independent TTLs.

    Each model can have its own configuration (device, TTL).
    Models are loaded lazily and unloaded independently based on their TTL.
    """

    def __init__(self, default_model: str | None = None) -> None:
        """Initialize the registry.

        Args:
            default_model: Name of the default model to use when not specified.

        """
        self._managers: dict[str, ManagerT] = {}
        self._default_model = default_model
        self._started = False

    @abstractmethod
    def _create_manager(self, config: ConfigT) -> ManagerT:
        """Create a manager instance from config."""
        ...

    @abstractmethod
    def _get_model_name(self, config: ConfigT) -> str:
        """Get the model name from config."""
        ...

    @abstractmethod
    def _get_manager_status(self, name: str, manager: ManagerT) -> StatusT:
        """Get status from a manager."""
        ...

    @abstractmethod
    async def _start_manager(self, manager: ManagerT) -> None:
        """Start a manager."""
        ...

    @abstractmethod
    async def _stop_manager(self, manager: ManagerT) -> None:
        """Stop a manager."""
        ...

    @abstractmethod
    async def _preload_manager(self, manager: ManagerT) -> None:
        """Preload a manager's model."""
        ...

    @abstractmethod
    def _is_manager_loaded(self, manager: ManagerT) -> bool:
        """Check if a manager's model is loaded."""
        ...

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

        Raises:
            ValueError: If a model with this name is already registered.

        """
        model_name = self._get_model_name(config)

        if model_name in self._managers:
            msg = f"Model '{model_name}' is already registered"
            raise ValueError(msg)

        manager = self._create_manager(config)
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

    def list_status(self) -> list[StatusT]:
        """Get status of all registered models."""
        return [self._get_manager_status(name, manager) for name, manager in self._managers.items()]

    async def start(self) -> None:
        """Start all model managers (TTL watchers)."""
        if self._started:
            return

        for manager in self._managers.values():
            await self._start_manager(manager)

        self._started = True
        logger.debug("Started registry with %d model(s)", len(self._managers))

    async def stop(self) -> None:
        """Stop all model managers and unload all models."""
        for manager in self._managers.values():
            await self._stop_manager(manager)

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
            if not self._is_manager_loaded(manager):
                logger.debug("Preloading model %s", name)
                await self._preload_manager(manager)
