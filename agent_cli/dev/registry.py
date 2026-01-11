"""Generic registry for adapter classes (editors, agents, terminals)."""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Generic registry for adapter instances with caching and detection."""

    def __init__(self, adapter_classes: list[type[T]]) -> None:
        """Initialize the registry with adapter classes.

        Args:
            adapter_classes: List of adapter classes in priority order for detection.

        """
        self._classes = adapter_classes
        self._instances: dict[str, T] = {}

    def get_all(self) -> list[T]:
        """Get instances of all registered adapters."""
        adapters = []
        for cls in self._classes:
            name = cls.name  # type: ignore[attr-defined]
            if name not in self._instances:
                self._instances[name] = cls()
            adapters.append(self._instances[name])
        return adapters

    def get_available(self) -> list[T]:
        """Get all installed/available adapters."""
        return [adapter for adapter in self.get_all() if adapter.is_available()]  # type: ignore[attr-defined]

    def detect_current(self) -> T | None:
        """Detect which adapter is currently active in the environment."""
        for adapter in self.get_all():
            if adapter.detect():  # type: ignore[attr-defined]
                return adapter
        return None

    def get_by_name(self, name: str) -> T | None:
        """Get an adapter by name or command."""
        name_lower = name.lower()
        for adapter in self.get_all():
            if adapter.name.lower() == name_lower:  # type: ignore[attr-defined]
                return adapter
            if hasattr(adapter, "command") and adapter.command.lower() == name_lower:  # type: ignore[attr-defined]
                return adapter
        return None
