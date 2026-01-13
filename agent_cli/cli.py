"""Shared CLI functionality for the Agent CLI tools."""

from __future__ import annotations

from typing import Annotated

import typer

from . import __version__
from .config import load_config, normalize_provider_defaults
from .core.utils import console

app = typer.Typer(
    name="agent-cli",
    help="A suite of AI-powered command-line tools for text correction, audio transcription, and voice assistance.",
    add_completion=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    rich_markup_mode="markdown",
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"agent-cli {__version__}")
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
    """A suite of AI-powered tools."""
    if ctx.invoked_subcommand is None:
        console.print("[bold red]No command specified.[/bold red]")
        console.print("[bold yellow]Running --help for your convenience.[/bold yellow]")
        console.print(ctx.get_help())
        raise typer.Exit
    import dotenv  # noqa: PLC0415

    dotenv.load_dotenv()


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
    server,
    speak,
    transcribe,
    transcribe_daemon,
    voice_edit,
)
from .dev import cli as dev_cli  # noqa: E402, F401
from .install import hotkeys, services  # noqa: E402, F401
