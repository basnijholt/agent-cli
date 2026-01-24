"""Helpers for optional dependency checks."""

from __future__ import annotations

import functools
from importlib.util import find_spec
from typing import TYPE_CHECKING, TypeVar

import typer

from agent_cli._extras import EXTRAS
from agent_cli.core.utils import print_error_message

if TYPE_CHECKING:
    from collections.abc import Callable

F = TypeVar("F", bound="Callable[..., object]")


def check_extra_installed(extra: str) -> bool:
    """Check if packages for an extra are installed using find_spec (no actual import)."""
    if extra not in EXTRAS:
        return True  # Unknown extra, assume OK
    _, packages = EXTRAS[extra]
    for pkg in packages:
        # Convert module path to top-level module for find_spec
        # e.g., "google.genai" -> check "google" first
        top_module = pkg.split(".")[0]
        try:
            if find_spec(top_module) is None:
                return False
        except (ValueError, ModuleNotFoundError):
            # find_spec can raise ValueError if module's __spec__ is not set
            # or ModuleNotFoundError for missing parent packages
            return False
    return True


def get_install_hint(extra: str) -> str:
    """Get install command hint for an extra."""
    desc, _ = EXTRAS.get(extra, ("", []))
    lines = [
        f"This command requires the '{extra}' extra",
    ]
    if desc:
        lines[0] += f" ({desc})"
    lines[0] += "."
    lines.append("")
    lines.append("Install with:")
    lines.append(f'  uv tool install "agent-cli[{extra}]" -p 3.13')
    lines.append("  # or")
    lines.append(f"  agent-cli install-extras {extra}")
    return "\n".join(lines)


def requires_extras(*extras: str) -> Callable[[F], F]:
    """Decorator to declare required extras for a command.

    When a required extra is missing, the decorator prints a helpful error
    message and exits with code 1.

    The decorator stores the required extras on the function for test validation.

    Process management flags (--stop, --status, --toggle) skip the dependency
    check since they just manage running processes without using the actual
    dependencies.

    Example:
        @app.command("rag-proxy")
        @requires_extras("rag")
        def rag_proxy(...):
            ...

    """

    def decorator(func: F) -> F:
        # Store extras on function for test introspection
        func._required_extras = extras  # type: ignore[attr-defined]

        @functools.wraps(func)
        def wrapper(*args: object, **kwargs: object) -> object:
            # Skip dependency check for process management and info operations
            # These don't need the actual dependencies, just manage processes or list info
            if any(kwargs.get(flag) for flag in ("stop", "status", "toggle", "list_devices")):
                return func(*args, **kwargs)

            missing = [e for e in extras if not check_extra_installed(e)]
            if missing:
                for extra in missing:
                    print_error_message(get_install_hint(extra))
                raise typer.Exit(1)
            return func(*args, **kwargs)

        # Preserve the extras on wrapper too
        wrapper._required_extras = extras  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
