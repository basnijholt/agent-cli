"""Install optional extras at runtime with pinned versions."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Annotated

import typer

from agent_cli.cli import app
from agent_cli.core.deps import EXTRAS as _EXTRAS_META
from agent_cli.core.utils import console, print_error_message

# Extract descriptions from the centralized EXTRAS metadata
EXTRAS: dict[str, str] = {name: desc for name, (desc, _) in _EXTRAS_META.items()}


def _requirements_dir() -> Path:
    return Path(__file__).parent.parent / "_requirements"


def _available_extras() -> list[str]:
    """List available extras based on requirements files."""
    req_dir = _requirements_dir()
    if not req_dir.exists():
        return []
    return sorted(p.stem for p in req_dir.glob("*.txt"))


def _requirements_path(extra: str) -> Path:
    return _requirements_dir() / f"{extra}.txt"


def _in_virtualenv() -> bool:
    """Check if running inside a virtual environment."""
    return sys.prefix != sys.base_prefix


def _is_uv_tool_install() -> bool:
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


def _install_via_uv_tool(extras: list[str]) -> bool:
    """Reinstall agent-cli via uv tool with the specified extras."""
    extras_str = ",".join(extras)
    package_spec = f"agent-cli[{extras_str}]"
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    console.print(f"Reinstalling via uv tool: [cyan]{package_spec}[/] (Python {python_version})")
    cmd = ["uv", "tool", "install", package_spec, "--force", "--python", python_version]
    result = subprocess.run(cmd, check=False)
    return result.returncode == 0


def _install_cmd() -> list[str]:
    """Build the install command with appropriate flags."""
    in_venv = _in_virtualenv()
    if shutil.which("uv"):
        cmd = ["uv", "pip", "install", "--python", sys.executable]
        if not in_venv:
            # Allow installing to system Python when not in a venv
            cmd.append("--system")
        return cmd
    cmd = [sys.executable, "-m", "pip", "install"]
    if not in_venv:
        # Install to user site-packages when not in a venv
        cmd.append("--user")
    return cmd


def _install_extras_impl(extras: list[str], *, quiet: bool = False) -> bool:
    """Install extras. Returns True on success, False on failure."""
    if _is_uv_tool_install():
        current_extras = _get_current_uv_tool_extras()
        new_extras = sorted(set(current_extras) | set(extras))
        return _install_via_uv_tool(new_extras)

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


def install_extras_programmatic(extras: list[str], *, quiet: bool = False) -> bool:
    """Install extras programmatically (for auto-install feature)."""
    valid = [e for e in extras if e in _available_extras()]
    return bool(valid) and _install_extras_impl(valid, quiet=quiet)


@app.command("install-extras", rich_help_panel="Installation")
def install_extras(
    extras: Annotated[list[str] | None, typer.Argument(help="Extras to install")] = None,
    list_extras: Annotated[
        bool,
        typer.Option("--list", "-l", help="List available extras"),
    ] = False,
    all_extras: Annotated[
        bool,
        typer.Option("--all", "-a", help="Install all available extras"),
    ] = False,
) -> None:
    """Install optional extras (rag, memory, vad, etc.) with pinned versions.

    Examples:
        agent-cli install-extras rag           # Install RAG dependencies
        agent-cli install-extras memory vad    # Install multiple extras
        agent-cli install-extras --list        # Show available extras
        agent-cli install-extras --all         # Install all extras

    """
    available = _available_extras()

    if list_extras:
        console.print("[bold]Available extras:[/]")
        for name in available:
            desc = EXTRAS.get(name, "")
            console.print(f"  [cyan]{name}[/]: {desc}")
        return

    if all_extras:
        extras = available

    if not extras:
        print_error_message("No extras specified. Use --list to see available, or --all.")
        raise typer.Exit(1)

    invalid = [e for e in extras if e not in available]
    if invalid:
        print_error_message(f"Unknown extras: {invalid}. Use --list to see available.")
        raise typer.Exit(1)

    if not _install_extras_impl(extras):
        print_error_message("Failed to install extras")
        raise typer.Exit(1)

    if _is_uv_tool_install():
        console.print("[green]Done! Extras will persist across uv tool upgrade.[/]")
    else:
        console.print("[green]Done![/]")
