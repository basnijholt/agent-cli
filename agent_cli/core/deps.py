"""Helpers for optional dependency checks."""

from __future__ import annotations

from importlib.util import find_spec


def ensure_optional_dependencies(
    required: dict[str, str],
    *,
    extra_name: str,
    install_hint: str | None = None,
) -> None:
    """Ensure optional dependencies are present, otherwise raise ImportError."""
    missing = [
        pkg_name for module_name, pkg_name in required.items() if find_spec(module_name) is None
    ]
    if not missing:
        return

    hint = install_hint or f"`pip install agent-cli[{extra_name}]`"
    msg = f"Missing required dependencies for {extra_name}: {', '.join(missing)}. Please install with {hint}."
    raise ImportError(msg)
