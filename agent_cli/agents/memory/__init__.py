"""Memory system CLI commands."""

from __future__ import annotations

import typer

from agent_cli.cli import app

memory_app = typer.Typer(
    name="memory",
    help="Memory system operations (add, list, proxy, etc.).",
    no_args_is_help=True,
)

app.add_typer(memory_app, name="memory")

# Import subcommands to register them with memory_app
from agent_cli.agents.memory import add, proxy  # noqa: E402

__all__ = ["add", "memory_app", "proxy"]
