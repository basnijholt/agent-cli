"""Shared CLI functionality for the Agent CLI tools."""

from __future__ import annotations

import typer

from .config import load_config
from .core.utils import console

app = typer.Typer(
    name="agent-cli",
    help="A suite of AI-powered command-line tools for text correction, audio transcription, and voice assistance.",
    add_completion=True,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
) -> None:
    """A suite of AI-powered tools."""
    if ctx.invoked_subcommand is None:
        console.print("[bold red]No command specified.[/bold red]")
        console.print("[bold yellow]Running --help for your convenience.[/bold yellow]")
        console.print(ctx.get_help())
        raise typer.Exit
    import dotenv  # noqa: PLC0415

    dotenv.load_dotenv()
    print()


def set_config_defaults(ctx: typer.Context, config_file: str | None) -> None:
    """Set the default values for the CLI based on the config file."""
    config = load_config(config_file)
    wildcard_config = config.get("defaults", {})
    subcommand = ctx.invoked_subcommand

    if not subcommand:
        ctx.default_map = wildcard_config
        return

    command_config = config.get(subcommand, {})
    defaults = {**wildcard_config, **command_config}
    ctx.default_map = defaults


# Import commands from other modules to register them
from .agents import assistant, autocorrect, chat, speak, transcribe, voice_edit  # noqa: E402, F401
