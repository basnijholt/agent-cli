"""Install optional extras at runtime with pinned versions."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from agent_cli.cli import app
from agent_cli.core.utils import console, print_error_message


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


def _install_cmd() -> list[str]:
    if shutil.which("uv"):
        return ["uv", "pip", "install", "--python", sys.executable]
    return [sys.executable, "-m", "pip", "install"]


@app.command("install-extras", rich_help_panel="Installation")
def install_extras(
    extras: Annotated[list[str] | None, typer.Argument(help="Extras to install")] = None,
    list_extras: Annotated[
        bool,
        typer.Option("--list", "-l", help="List available extras"),
    ] = False,
    upgrade: Annotated[bool, typer.Option("--upgrade", "-U", help="Upgrade packages")] = False,
) -> None:
    """Install optional extras (rag, memory, vad, etc.) with pinned versions.

    Examples:
        agent-cli install-extras rag           # Install RAG dependencies
        agent-cli install-extras memory vad    # Install multiple extras
        agent-cli install-extras --list        # Show available extras

    """
    available = _available_extras()

    if list_extras:
        console.print("[bold]Available extras:[/]")
        for name in available:
            console.print(f"  [cyan]{name}[/]")
        return

    if not extras:
        print_error_message("No extras specified. Use --list to see available.")
        raise typer.Exit(1)

    invalid = [e for e in extras if e not in available]
    if invalid:
        print_error_message(f"Unknown extras: {invalid}. Use --list to see available.")
        raise typer.Exit(1)

    cmd = _install_cmd()
    if upgrade:
        cmd.append("--upgrade")

    for extra in extras:
        req_file = _requirements_path(extra)
        console.print(f"Installing [cyan]{extra}[/]...")
        result = subprocess.run([*cmd, "-r", str(req_file)], check=False)
        if result.returncode != 0:
            print_error_message(f"Failed to install '{extra}'")
            raise typer.Exit(1)

    console.print("[green]Done![/]")
