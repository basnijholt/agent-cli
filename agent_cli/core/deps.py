"""Helpers for optional dependency checks."""

from __future__ import annotations

import functools
import json
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import typer

from agent_cli.core.utils import print_error_message

if TYPE_CHECKING:
    from collections.abc import Callable

F = TypeVar("F", bound="Callable[..., object]")

# Load extras from JSON file
_EXTRAS_FILE = Path(__file__).parent.parent / "_extras.json"
EXTRAS: dict[str, tuple[str, list[str]]] = {
    k: (v[0], v[1]) for k, v in json.loads(_EXTRAS_FILE.read_text()).items()
}


def _check_package_installed(pkg: str) -> bool:
    """Check if a single package is installed."""
    top_module = pkg.split(".")[0]
    try:
        return find_spec(top_module) is not None
    except (ValueError, ModuleNotFoundError):
        return False


# Extras where ANY package being installed is sufficient (platform-specific)
_ANY_OF_EXTRAS = {"whisper"}


def check_extra_installed(extra: str) -> bool:
    """Check if packages for an extra are installed using find_spec (no actual import).

    Supports `|` syntax for alternatives: "tts|tts-kokoro" means ANY of these extras.
    For platform-specific extras (whisper), ANY package being installed is sufficient.
    For regular extras, ALL packages must be installed.
    """
    # Handle "extra1|extra2" syntax - any of these extras is sufficient
    if "|" in extra:
        return any(check_extra_installed(e) for e in extra.split("|"))

    if extra not in EXTRAS:
        return True  # Unknown extra, assume OK
    _, packages = EXTRAS[extra]

    if extra in _ANY_OF_EXTRAS:
        # For platform-specific extras, any one package is sufficient
        return any(_check_package_installed(pkg) for pkg in packages)

    # For regular extras, all packages must be installed
    return all(_check_package_installed(pkg) for pkg in packages)


def get_install_hint(extra: str) -> str:
    """Get install command hint for an extra.

    Supports `|` syntax for alternatives: "tts|tts-kokoro" shows both options.
    """
    # Handle "extra1|extra2" syntax - show all options
    if "|" in extra:
        alternatives = extra.split("|")
        options = []
        for alt in alternatives:
            desc, _ = EXTRAS.get(alt, ("", []))
            options.append((alt, desc))

        lines = ["This command requires one of:"]
        for alt, desc in options:
            if desc:
                lines.append(f"  - '{alt}' ({desc})")
            else:
                lines.append(f"  - '{alt}'")
        lines.append("")
        lines.append("Install one with:")
        for alt, _ in options:
            lines.append(f'  uv tool install "agent-cli[{alt}]" -p 3.13')
        lines.append("  # or")
        for alt, _ in options:
            lines.append(f"  agent-cli install-extras {alt}")
        return "\n".join(lines)

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
