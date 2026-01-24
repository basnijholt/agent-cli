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

EXTRAS = {
    "rag": "RAG proxy (ChromaDB, embeddings)",
    "memory": "Long-term memory proxy",
    "vad": "Voice Activity Detection",
    "whisper": "Local Whisper ASR",
    "whisper-mlx": "MLX Whisper (Apple Silicon)",
    "tts": "Local Piper TTS",
    "tts-kokoro": "Kokoro neural TTS",
    "server": "FastAPI server components",
}


def _requirements_dir() -> Path:
    return Path(__file__).parent.parent / "_requirements"


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
    if list_extras:
        console.print("[bold]Available extras:[/]")
        for name, desc in EXTRAS.items():
            req_file = _requirements_path(name)
            status = "[green]✓[/]" if req_file.exists() else "[red]✗[/]"
            console.print(f"  {status} [cyan]{name}[/]: {desc}")
        return

    if not extras:
        print_error_message("No extras specified. Use --list to see available.")
        raise typer.Exit(1)

    invalid = [e for e in extras if e not in EXTRAS]
    if invalid:
        print_error_message(f"Unknown extras: {invalid}. Use --list to see available.")
        raise typer.Exit(1)

    cmd = _install_cmd()
    if upgrade:
        cmd.append("--upgrade")

    for extra in extras:
        req_file = _requirements_path(extra)
        if not req_file.exists():
            print_error_message(
                f"Requirements file missing for '{extra}'. "
                "Run 'python .github/scripts/sync_requirements.py' to generate.",
            )
            raise typer.Exit(1)
        console.print(f"Installing [cyan]{extra}[/]...")
        result = subprocess.run([*cmd, "-r", str(req_file)], check=False)
        if result.returncode != 0:
            print_error_message(f"Failed to install '{extra}'")
            raise typer.Exit(1)

    console.print("[green]Done![/]")
