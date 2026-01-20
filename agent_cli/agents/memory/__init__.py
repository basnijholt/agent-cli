"""Memory system CLI commands."""

from __future__ import annotations

import typer

from agent_cli.cli import app
from agent_cli.core.process import set_process_title

memory_app = typer.Typer(
    name="memory",
    help="Memory system operations (add, proxy, etc.).",
    rich_markup_mode="markdown",
    no_args_is_help=True,
)

app.add_typer(memory_app, name="memory", rich_help_panel="Servers")


@memory_app.callback()
def memory_callback(ctx: typer.Context) -> None:
    """Memory command group callback."""
    if ctx.invoked_subcommand is not None:
        set_process_title(f"memory-{ctx.invoked_subcommand}")


# Import subcommands to register them with memory_app
from agent_cli.agents.memory import add, proxy  # noqa: E402

__all__ = ["add", "memory_app", "proxy"]
