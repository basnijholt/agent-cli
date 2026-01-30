"""Shared CLI functionality for the Agent CLI tools."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from . import __version__
from .config import load_config, normalize_provider_defaults
from .core.process import set_process_title
from .core.utils import console

_HELP = """\
AI-powered voice, text, and development tools.

**Voice & Text:**

- **Voice-to-text** - Transcribe speech with optional LLM cleanup
- **Text-to-speech** - Convert text to natural-sounding audio
- **Voice chat** - Conversational AI with memory and tool use
- **Text correction** - Fix grammar, spelling, and punctuation

**Development:**

- **Parallel development** - Git worktrees with integrated coding agents
- **Local servers** - ASR/TTS with Wyoming + OpenAI-compatible APIs,
  MLX on macOS ARM, CUDA/CPU Whisper, and automatic model TTL

**Provider Flexibility:**

Mix local (Ollama, Wyoming) and cloud (OpenAI, Gemini) backends freely.

Run `agent-cli <command> --help` for detailed command documentation.
"""

app = typer.Typer(
    name="agent-cli",
    help=_HELP,
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=True,
    rich_markup_mode="markdown",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        path = Path(__file__).parent
        data = [
            ("agent-cli version", __version__),
            ("agent-cli location", str(path)),
            ("Python version", sys.version),
            ("Python executable", sys.executable),
        ]
        table = Table(show_header=False)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="magenta")
        for prop, val in data:
            table.add_row(prop, val)
        console.print(table)
        raise typer.Exit


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[  # noqa: ARG001
        bool,
        typer.Option(
            "-v",
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """AI-powered voice, text, and development tools."""
    if ctx.invoked_subcommand is None:
        console.print("[bold red]No command specified.[/bold red]")
        console.print("[bold yellow]Running --help for your convenience.[/bold yellow]")
        console.print(ctx.get_help())
        raise typer.Exit
    import dotenv  # noqa: PLC0415

    dotenv.load_dotenv()

    # Set process title for identification in ps output
    set_process_title(ctx.invoked_subcommand)


def set_config_defaults(ctx: typer.Context, config_file: str | None) -> None:
    """Set the default values for the CLI based on the config file."""
    config = load_config(config_file)
    wildcard_config = normalize_provider_defaults(config.get("defaults", {}))

    command_key = ctx.command.name or ""
    if not command_key:
        ctx.default_map = wildcard_config
        return

    # For nested subcommands (e.g., "memory proxy"), build "memory.proxy"
    if ctx.parent and ctx.parent.command.name and ctx.parent.command.name != "agent-cli":
        command_key = f"{ctx.parent.command.name}.{command_key}"

    command_config = normalize_provider_defaults(config.get(command_key, {}))
    ctx.default_map = {**wildcard_config, **command_config}


# Import commands from other modules to register them
from . import config_cmd  # noqa: E402, F401
from .agents import (  # noqa: E402, F401
    assistant,
    autocorrect,
    chat,
    memory,
    rag_proxy,
    speak,
    transcribe,
    transcribe_daemon,
    voice_edit,
)
from .dev import cli as dev_cli  # noqa: E402, F401
from .install import extras, hotkeys, services  # noqa: E402, F401
from .server import cli as server_cli  # noqa: E402, F401
