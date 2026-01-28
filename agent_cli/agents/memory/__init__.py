"""Memory system CLI commands."""

from __future__ import annotations

import typer

from agent_cli.cli import app
from agent_cli.core.process import set_process_title

memory_app = typer.Typer(
    name="memory",
    help="""Long-term memory system for AI chat applications.

Provides persistent memory across conversations by storing facts and context
in Markdown files, with automatic vector indexing for semantic retrieval.

**Subcommands:**

- `proxy`: Start an OpenAI-compatible proxy that injects relevant memories
  into chat requests and extracts new facts from responses
- `add`: Manually add facts/memories without going through LLM extraction

**Quick Start:**

    # Start the memory proxy (point your chat client at localhost:8100)
    agent-cli memory proxy --openai-base-url http://localhost:11434/v1

    # Manually seed some memories
    agent-cli memory add "User prefers dark mode" "User is a Python developer"
""",
    add_completion=True,
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
