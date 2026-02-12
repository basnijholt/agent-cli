"""Helpers for optional dependency checks."""

from __future__ import annotations

import functools
import importlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import typer

from agent_cli.config import load_config
from agent_cli.core.utils import console, err_console, print_error_message

if TYPE_CHECKING:
    from collections.abc import Callable

F = TypeVar("F", bound="Callable[..., object]")

# Marker to prevent infinite re-exec loops
_REEXEC_MARKER = "_AGENT_CLI_REEXEC"


# -- Settings --


def _get_auto_install_setting() -> bool:
    """Check if auto-install is enabled (default: True)."""
    if os.environ.get("AGENT_CLI_NO_AUTO_INSTALL", "").lower() in ("1", "true", "yes"):
        return False
    return load_config().get("settings", {}).get("auto_install_extras", True)


# -- Environment Detection --


def _is_uvx_cache() -> bool:
    """Check if running from uvx cache (ephemeral) vs uv tool (persistent)."""
    # uvx uses ~/.cache/uv/archive-v0/... (or AppData\Local\uv\cache on Windows)
    # uv tool uses ~/.local/share/uv/tools/... (or AppData\Local\uv\tools on Windows)
    # Use as_posix() for cross-platform forward-slash paths
    prefix_str = Path(sys.prefix).resolve().as_posix()
    return "/cache/uv/" in prefix_str or "/archive-v" in prefix_str


# -- Package Checking --

# Load extras from JSON file
_EXTRAS_FILE = Path(__file__).parent.parent / "_extras.json"
EXTRAS: dict[str, tuple[str, list[str]]] = {
    k: (v[0], v[1]) for k, v in json.loads(_EXTRAS_FILE.read_text()).items()
}


def _check_package_installed(pkg: str) -> bool:
    """Check if a single package is installed."""
    top_module = pkg.split(".", maxsplit=1)[0]
    try:
        return find_spec(top_module) is not None
    except (ValueError, ModuleNotFoundError):
        return False


def _check_extra_installed(extra: str) -> bool:
    """Check if packages for an extra are installed using find_spec (no actual import).

    Supports `|` syntax for alternatives: "piper|kokoro" means ANY of these extras.
    For regular extras, ALL packages must be installed.
    """
    # Handle "extra1|extra2" syntax - any of these extras is sufficient
    if "|" in extra:
        return any(_check_extra_installed(e) for e in extra.split("|"))

    if extra not in EXTRAS:
        return False  # Unknown extra, trigger install attempt to surface error
    _, packages = EXTRAS[extra]

    # All packages must be installed
    return all(_check_package_installed(pkg) for pkg in packages)


# -- Formatting (for error messages) --


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
        f'  [bold cyan]uv tool install "agent-cli\\[{combined}]"[/bold cyan]',
        "  # or",
        f"  [bold cyan]agent-cli install-extras {extras_args}[/bold cyan]",
    ]


def _get_install_hint(extra: str) -> str:
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
            f'  [bold cyan]uv tool install "agent-cli\\[{alt}]"[/bold cyan]' for alt in alternatives
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
        return _get_install_hint(extras[0])

    lines = ["This command requires the following extras:"]
    lines.extend(_format_extra_item(extra) for extra in extras)
    lines.append("")
    lines.extend(_format_install_commands(extras))
    return "\n".join(lines)


# -- Installation --

_REQUIREMENTS_DIR = Path(__file__).parent.parent / "_requirements"


def available_extras() -> list[str]:
    """List available extras based on requirements files."""
    if not _REQUIREMENTS_DIR.exists():
        return []
    return sorted(p.stem for p in _REQUIREMENTS_DIR.glob("*.txt"))


def _requirements_path(extra: str) -> Path:
    """Get the requirements file path for an extra."""
    return _REQUIREMENTS_DIR / f"{extra}.txt"


def _in_virtualenv() -> bool:
    """Check if running inside a virtual environment."""
    return sys.prefix != sys.base_prefix


def is_uv_tool_install() -> bool:
    """Check if running from a uv tool environment."""
    receipt = Path(sys.prefix) / "uv-receipt.toml"
    return receipt.exists()


def _get_current_uv_tool_extras() -> list[str]:
    """Get extras currently configured in uv-receipt.toml."""
    receipt = Path(sys.prefix) / "uv-receipt.toml"
    if not receipt.exists():
        return []
    data = tomllib.loads(receipt.read_text())
    requirements = data.get("tool", {}).get("requirements", [])
    for req in requirements:
        if req.get("name") == "agent-cli":
            return req.get("extras", [])
    return []


def _install_via_uv_tool(extras: list[str], *, quiet: bool = False) -> bool:
    """Reinstall agent-cli via uv tool with the specified extras."""
    extras_str = ",".join(extras)
    package_spec = f"agent-cli[{extras_str}]"
    cmd = ["uv", "tool", "install", package_spec, "--force"]
    if quiet:
        cmd.append("-q")
    # Use stderr for status messages so they don't pollute stdout
    cmd_str = " ".join(cmd).replace("[", r"\[")
    err_console.print(f"Running: [cyan]{cmd_str}[/]")
    result = subprocess.run(cmd, check=False)
    return result.returncode == 0


def _install_cmd() -> list[str]:
    """Build the install command with appropriate flags."""
    in_venv = _in_virtualenv()
    if shutil.which("uv"):
        cmd = ["uv", "pip", "install", "--python", sys.executable]
        if not in_venv:
            cmd.append("--system")
        return cmd
    cmd = [sys.executable, "-m", "pip", "install"]
    if not in_venv:
        cmd.append("--user")
    return cmd


def install_extras_impl(extras: list[str], *, quiet: bool = False) -> bool:
    """Install extras. Returns True on success, False on failure."""
    if is_uv_tool_install():
        current_extras = _get_current_uv_tool_extras()
        new_extras = sorted(set(current_extras) | set(extras))
        return _install_via_uv_tool(new_extras, quiet=quiet)

    cmd = _install_cmd()
    for extra in extras:
        req_file = _requirements_path(extra)
        if not quiet:
            console.print(f"Installing [cyan]{extra}[/]...")
        result = subprocess.run(
            [*cmd, "-r", str(req_file)],
            check=False,
            capture_output=quiet,
        )
        if result.returncode != 0:
            return False
    return True


def _install_extras_programmatic(extras: list[str], *, quiet: bool = False) -> bool:
    """Install extras programmatically (for auto-install feature)."""
    available = available_extras()
    valid = [e for e in extras if e in available]
    invalid = [e for e in extras if e not in available]
    if invalid:
        err_console.print(f"[yellow]Unknown extras (skipped): {', '.join(invalid)}[/]")
    return bool(valid) and install_extras_impl(valid, quiet=quiet)


def _resolve_extras_for_install(extras: tuple[str, ...]) -> list[str]:
    """Normalize extras: resolve 'a|b' alternatives to concrete extras.

    For alternatives, uses the installed one if present, otherwise first option.
    """
    result = []
    for extra in extras:
        if "|" in extra:
            alternatives = extra.split("|")
            installed = next((a for a in alternatives if _check_extra_installed(a)), None)
            result.append(installed or alternatives[0])
        else:
            result.append(extra)
    return result


def _maybe_exec_with_marker(cmd: list[str], message: str) -> None:
    """Re-execute with a new command, preventing infinite loops."""
    if os.environ.get(_REEXEC_MARKER):
        return
    err_console.print(f"[yellow]{message}[/]")
    new_env = os.environ.copy()
    new_env[_REEXEC_MARKER] = "1"
    os.execvpe(cmd[0], cmd, new_env)  # noqa: S606


def _maybe_reexec_with_uvx(extras: list[str]) -> None:
    """Try to re-execute with uvx running agent-cli[extras] directly.

    If successful, replaces the current process (never returns).
    If not in uvx cache or uvx unavailable, returns normally.
    """
    if os.environ.get(_REEXEC_MARKER) or not _is_uvx_cache():
        return
    uvx_path = shutil.which("uvx")
    if not uvx_path:
        return
    extras_str = ",".join(extras)
    cmd = [uvx_path, f"agent-cli[{extras_str}]", *sys.argv[1:]]
    _maybe_exec_with_marker(cmd, f"Re-running with extras: {extras_str}")


def _try_auto_install(missing_display: list[str], extras_to_install: list[str]) -> bool:
    """Attempt to auto-install extras. Returns True if successful."""
    err_console.print(
        f"[yellow]Auto-installing missing extras: {', '.join(missing_display)}[/]",
    )
    return _install_extras_programmatic(extras_to_install, quiet=True)


def _maybe_reexec_after_install() -> None:
    """Re-execute after auto-install so new packages are visible."""
    executable = shutil.which("agent-cli") or sys.executable
    _maybe_exec_with_marker([executable, *sys.argv[1:]], "Re-running with installed extras...")


# -- Main Orchestration --


def _check_and_install_extras(extras: tuple[str, ...]) -> list[str]:
    """Check for missing extras and attempt auto-install. Returns list of still-missing."""
    # 1. Check what's missing
    missing = [e for e in extras if not _check_extra_installed(e)]
    if not missing:
        return []

    # 2. Auto-install disabled? Show error and return missing
    if not _get_auto_install_setting():
        print_error_message(get_combined_install_hint(missing))
        return missing

    # 3. Resolve alternatives for installation (normalize once)
    extras_to_install = _resolve_extras_for_install(extras)
    missing_display = _resolve_extras_for_install(tuple(missing))

    # 4. Try uvx re-exec (replaces process if successful)
    if _is_uvx_cache():
        _maybe_reexec_with_uvx(extras_to_install)  # may not return

    # 5. Try normal auto-install
    if not _try_auto_install(missing_display, extras_to_install):
        print_error_message("Auto-install failed.\n" + get_combined_install_hint(missing))
        return missing

    err_console.print("[green]Installation complete![/]")

    # 6. Re-exec to pick up new packages (may not return)
    _maybe_reexec_after_install()

    # 7. If we're here, re-exec was skipped - check if packages are now visible
    importlib.invalidate_caches()
    still_missing = [e for e in extras if not _check_extra_installed(e)]
    if still_missing:
        print_error_message(
            "Extras installed but not visible (restart may be needed).\n"
            + get_combined_install_hint(still_missing),
        )
    return still_missing


# -- Decorator --


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
