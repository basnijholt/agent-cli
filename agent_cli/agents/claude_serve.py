"""Claude Code remote server command for Agent CLI."""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path

import typer

from agent_cli import opts
from agent_cli.cli import app
from agent_cli.core.utils import (
    console,
    print_command_line_args,
    print_error_message,
)

has_uvicorn = find_spec("uvicorn") is not None
has_fastapi = find_spec("fastapi") is not None
has_claude_sdk = find_spec("claude_agent_sdk") is not None


def run_claude_server(
    host: str = "0.0.0.0",  # noqa: S104
    port: int = 8765,
    reload: bool = False,
    cwd: Path | None = None,
) -> None:
    """Run the Claude Code FastAPI server."""
    import os  # noqa: PLC0415

    import uvicorn  # noqa: PLC0415

    # Set working directory for the API to use
    if cwd:
        os.environ["CLAUDE_API_CWD"] = str(cwd.resolve())

    uvicorn.run(
        "agent_cli.claude_api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command("claude-serve")
def claude_serve(
    host: str = typer.Option(
        "0.0.0.0",  # noqa: S104
        help="Host to bind the server to",
    ),
    port: int = typer.Option(8765, help="Port to bind the server to"),
    cwd: Path = typer.Option(  # noqa: B008
        None,
        help="Working directory for Claude Code (defaults to current directory)",
    ),
    reload: bool = typer.Option(
        False,  # noqa: FBT003
        "--reload",
        help="Enable auto-reload for development",
    ),
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Start Claude Code remote server for iOS/web access.

    This starts a FastAPI server that exposes Claude Code capabilities via REST and WebSocket
    endpoints, allowing remote access from iOS Shortcuts, web interfaces, or any HTTP client.

    Prerequisites:
    - Run `claude /login` once to authenticate with your Claude.ai account
    - Install dependencies: pip install agent-cli[claude]

    Example usage:
        agent-cli claude-serve --port 8765 --cwd /path/to/project

    Endpoints:
    - POST /session/new - Create a new Claude Code session
    - POST /session/{id}/prompt - Send a prompt and get result
    - POST /session/{id}/cancel - Cancel current operation
    - WS /session/{id}/stream - WebSocket for streaming responses
    - GET /health - Health check
    """
    if print_args:
        print_command_line_args(locals())

    if not has_uvicorn or not has_fastapi:
        msg = (
            "uvicorn or fastapi is not installed. "
            "Please install with: pip install agent-cli[claude]"
        )
        print_error_message(msg)
        raise typer.Exit(1)

    if not has_claude_sdk:
        msg = (
            "claude-agent-sdk is not installed. Please install with: pip install agent-cli[claude]"
        )
        print_error_message(msg)
        raise typer.Exit(1)

    # Default to current directory if not specified
    if cwd is None:
        cwd = Path.cwd()

    console.print(
        f"[bold green]Starting Claude Code remote server on {host}:{port}[/bold green]",
    )
    console.print(f"[dim]Working directory: {cwd.resolve()}[/dim]")
    console.print()
    console.print("[bold]Endpoints:[/bold]")
    console.print(f"  POST http://{host}:{port}/session/new")
    console.print(f"  POST http://{host}:{port}/session/{{id}}/prompt")
    console.print(f"  WS   ws://{host}:{port}/session/{{id}}/stream")
    console.print()

    if reload:
        console.print("[yellow]Auto-reload enabled for development[/yellow]")

    run_claude_server(host=host, port=port, reload=reload, cwd=cwd)
