"""Shared CLI functionality for the Agent CLI tools."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import typer

from .config_loader import load_config
from .utils import console

if TYPE_CHECKING:
    from logging import Handler


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


def set_config_defaults(ctx: typer.Context, config_file: str | None) -> None:  # noqa: PLR0912
    """Set the default values for the CLI based on the config file."""
    config = load_config(config_file)
    if not config:
        return

    # Flatten the provider-specific configs from sections like [llm.openai]
    flat_provider_config = {}
    for service, providers in config.items():
        if service in {"llm", "asr", "tts"} and isinstance(providers, dict):
            for provider, params in providers.items():
                if isinstance(params, dict):
                    for param, value in params.items():
                        # Maps e.g. [llm.openai] model="gpt-4" to "llm_openai_model"
                        key = f"{service}_{provider}_{param}"
                        flat_provider_config[key] = value

    # Get command-specific overrides and top-level defaults
    command_config = config.get(ctx.invoked_subcommand, {}) if ctx.invoked_subcommand else {}
    defaults_config = config.get("defaults", {})

    # Combine them in order of precedence: command > defaults > provider-specific
    final_defaults = {**flat_provider_config, **defaults_config}
    if command_config:
        for section, settings in command_config.items():
            if isinstance(settings, dict):
                # Flatten command-specific provider settings
                if section in {"llm", "asr", "tts"}:
                    for provider, params in settings.items():
                        if isinstance(params, dict):
                            for param, p_value in params.items():
                                final_defaults[f"{section}_{provider}_{param}"] = p_value
                else:
                    for key, value in settings.items():
                        final_defaults[key] = value  # noqa: PERF403

    # Set the default_map for the Typer context, which it uses to set defaults
    # for all parameters.
    ctx.default_map = final_defaults

    # Set the default_map for the Typer context, which it uses to set defaults
    # for all parameters.
    ctx.default_map = final_defaults


def setup_logging(log_level: str, log_file: str | None, *, quiet: bool) -> None:
    """Sets up logging based on parsed arguments."""
    handlers: list[Handler] = []
    if not quiet:
        handlers.append(logging.StreamHandler())
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode="w"))

    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


# Import commands from other modules to register them
from .agents import (  # noqa: E402, F401
    autocorrect,
    interactive,
    speak,
    transcribe,
    voice_assistant,
    wake_word_assistant,
)
