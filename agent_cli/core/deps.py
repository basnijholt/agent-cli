"""Helpers for optional dependency checks."""

from __future__ import annotations

import functools
import importlib
import json
import os
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import typer

from agent_cli.config import load_config
from agent_cli.core.utils import err_console, print_error_message

if TYPE_CHECKING:
    from collections.abc import Callable

F = TypeVar("F", bound="Callable[..., object]")


def _get_auto_install_setting() -> bool:
    """Check if auto-install is enabled (default: True)."""
    if os.environ.get("AGENT_CLI_NO_AUTO_INSTALL", "").lower() in ("1", "true", "yes"):
        return False
    return load_config().get("settings", {}).get("auto_install_extras", True)


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


def check_extra_installed(extra: str) -> bool:
    """Check if packages for an extra are installed using find_spec (no actual import).

    Supports `|` syntax for alternatives: "piper|kokoro" means ANY of these extras.
    For regular extras, ALL packages must be installed.
    """
    # Handle "extra1|extra2" syntax - any of these extras is sufficient
    if "|" in extra:
        return any(check_extra_installed(e) for e in extra.split("|"))

    if extra not in EXTRAS:
        return False  # Unknown extra, trigger install attempt to surface error
    _, packages = EXTRAS[extra]

    # All packages must be installed
    return all(_check_package_installed(pkg) for pkg in packages)


def _format_extra_item(extra: str) -> str:
    """Format a single extra as a list item with description."""
    desc, _ = EXTRAS.get(extra, ("", []))
    if desc:
        return f"  - '{extra}' ({desc})"
    return f"  - '{extra}'"


def _format_install_commands(extras: list[str]) -> list[str]:
    """Format install commands for one or more extras."""
    combined = ",".join(extras)
    extras_args = " ".join(extras)
    return [
        "Install with:",
        f'  [bold cyan]uv tool install -p 3.13 "agent-cli\\[{combined}]"[/bold cyan]',
        "  # or",
        f"  [bold cyan]agent-cli install-extras {extras_args}[/bold cyan]",
    ]


def get_install_hint(extra: str) -> str:
    """Get install command hint for a single extra.

    Supports `|` syntax for alternatives: "piper|kokoro" shows both options.
    """
    # Handle "extra1|extra2" syntax - show all options
    if "|" in extra:
        alternatives = extra.split("|")
        lines = ["This command requires one of:"]
        lines.extend(_format_extra_item(alt) for alt in alternatives)
        lines.append("")
        lines.append("Install one with:")
        lines.extend(
            f'  [bold cyan]uv tool install -p 3.13 "agent-cli\\[{alt}]"[/bold cyan]'
            for alt in alternatives
        )
        lines.append("  # or")
        lines.extend(
            f"  [bold cyan]agent-cli install-extras {alt}[/bold cyan]" for alt in alternatives
        )
        return "\n".join(lines)

    desc, _ = EXTRAS.get(extra, ("", []))
    header = f"This command requires the '{extra}' extra"
    if desc:
        header += f" ({desc})"
    header += "."

    lines = [header, ""]
    lines.extend(_format_install_commands([extra]))
    return "\n".join(lines)


def get_combined_install_hint(extras: list[str]) -> str:
    """Get a combined install hint for multiple missing extras."""
    if len(extras) == 1:
        return get_install_hint(extras[0])

    lines = ["This command requires the following extras:"]
    lines.extend(_format_extra_item(extra) for extra in extras)
    lines.append("")
    lines.extend(_format_install_commands(extras))
    return "\n".join(lines)


def _try_auto_install(missing: list[str]) -> bool:
    """Attempt to auto-install missing extras. Returns True if successful."""
    from agent_cli.install.extras import install_extras_programmatic  # noqa: PLC0415

    # Flatten alternatives (e.g., "piper|kokoro" -> just pick the first one)
    extras_to_install = []
    for extra in missing:
        if "|" in extra:
            # For alternatives, install the first option
            extras_to_install.append(extra.split("|")[0])
        else:
            extras_to_install.append(extra)

    err_console.print(
        f"[yellow]Auto-installing missing extras: {', '.join(extras_to_install)}[/]",
    )
    return install_extras_programmatic(extras_to_install, quiet=True)


def _check_and_install_extras(extras: tuple[str, ...]) -> list[str]:
    """Check for missing extras and attempt auto-install. Returns list of still-missing."""
    missing = [e for e in extras if not check_extra_installed(e)]
    if not missing:
        return []

    if not _get_auto_install_setting():
        print_error_message(get_combined_install_hint(missing))
        return missing

    if not _try_auto_install(missing):
        print_error_message("Auto-install failed.\n" + get_combined_install_hint(missing))
        return missing

    err_console.print("[green]Installation complete![/]")
    # Invalidate import caches so find_spec() can see newly installed packages
    importlib.invalidate_caches()
    still_missing = [e for e in extras if not check_extra_installed(e)]
    if still_missing:
        print_error_message(
            "Auto-install completed but some dependencies are still missing.\n"
            + get_combined_install_hint(still_missing),
        )
    return still_missing


def requires_extras(*extras: str) -> Callable[[F], F]:
    """Decorator to declare required extras for a command.

    Auto-installs missing extras by default. Disable via AGENT_CLI_NO_AUTO_INSTALL=1
    or config [settings] auto_install_extras = false.
    """

    def decorator(func: F) -> F:
        func._required_extras = extras  # type: ignore[attr-defined]

        @functools.wraps(func)
        def wrapper(*args: object, **kwargs: object) -> object:
            if _check_and_install_extras(extras):
                raise typer.Exit(1)
            return func(*args, **kwargs)

        wrapper._required_extras = extras  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
