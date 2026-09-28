"""Shared CLI functionality for the Agent CLI tools."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table
from typer.core import TyperGroup
from typer.main import get_command

from .config import load_config, normalize_provider_defaults
from .core.process import set_process_title
from .core.utils import console

_COMMAND_MODULES = {
    "assistant": "agent_cli.agents.assistant",
    "autocorrect": "agent_cli.agents.autocorrect",
    "chat": "agent_cli.agents.chat",
    "config": "agent_cli.config_cmd",
    "daemon": "agent_cli.daemon.cli",
    "dev": "agent_cli.dev.cli",
    "diarize-live-session": "agent_cli.agents.diarize_live_session",
    "install-extras": "agent_cli.install.extras",
    "install-hotkeys": "agent_cli.install.hotkeys",
    "install-services": "agent_cli.install.services",
    "memory": "agent_cli.agents.memory",
    "rag-proxy": "agent_cli.agents.rag_proxy",
    "server": "agent_cli.server.cli",
    "speak": "agent_cli.agents.speak",
    "speakers": "agent_cli.agents.speakers",
    "start-services": "agent_cli.install.services",
    "transcribe": "agent_cli.agents.transcribe",
    "transcribe-live": "agent_cli.agents.transcribe_live",
    "voice-edit": "agent_cli.agents.voice_edit",
}


class _LazyCommandGroup(TyperGroup):
    """Build command options only when selected, including help and completion."""

    def list_commands(self, ctx: typer.Context) -> list[str]:
        # Help and shell completion need the complete command catalogue.
        for module in dict.fromkeys(_COMMAND_MODULES.values()):
            importlib.import_module(module)
        return sorted(set(super().list_commands(ctx)) | _COMMAND_MODULES.keys())

    def get_command(self, ctx: typer.Context, cmd_name: str) -> Any:
        command = super().get_command(ctx, cmd_name)
        if command is None and (module := _COMMAND_MODULES.get(cmd_name)):
            importlib.import_module(module)
            # Command decorators register on app. Rebuild only the loaded subset,
            # then cache its commands on this invocation's Click group.
            group = get_command(app)
            assert isinstance(group, TyperGroup)
            self.commands.update(group.commands)
            command = super().get_command(ctx, cmd_name)
        return command


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
    cls=_LazyCommandGroup,
    name="agent-cli",
    help=_HELP,
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=True,
    rich_markup_mode="markdown",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        from . import __version__  # noqa: PLC0415

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


def set_config_defaults(ctx: typer.Context, config_file: str | None) -> dict[str, Any]:
    """Set the default values for the CLI based on the config file."""
    config = load_config(config_file)
    wildcard_config = normalize_provider_defaults(config.get("defaults", {}))

    command_key = ctx.command.name or ""
    if not command_key:
        ctx.default_map = wildcard_config
        return config

    parent_config: dict[str, Any] = {}

    # For nested subcommands (e.g., "memory proxy"), build "memory.proxy"
    # and apply the parent section as shared defaults for its subcommands.
    if ctx.parent and ctx.parent.command.name and ctx.parent.command.name != "agent-cli":
        parent_key = ctx.parent.command.name
        command_key = f"{parent_key}.{command_key}"
        parent_config = normalize_provider_defaults(config.get(parent_key, {}))

    command_config = normalize_provider_defaults(config.get(command_key, {}))
    ctx.default_map = {**wildcard_config, **parent_config, **command_config}
    return config
