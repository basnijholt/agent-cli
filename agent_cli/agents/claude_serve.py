"""Claude Code remote server command for Agent CLI."""

from __future__ import annotations

import json
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
    projects: dict[str, str] | None = None,
    default_project: str | None = None,
) -> None:
    """Run the Claude Code FastAPI server."""
    import os  # noqa: PLC0415

    import uvicorn  # noqa: PLC0415

    # Set working directory for the API to use
    if cwd:
        os.environ["CLAUDE_API_CWD"] = str(cwd.resolve())

    # Pass projects config via environment variable
    if projects:
        os.environ["CLAUDE_API_PROJECTS"] = json.dumps(projects)
    if default_project:
        os.environ["CLAUDE_API_DEFAULT_PROJECT"] = default_project

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
        agent-cli claude-serve --port 8765

    Configure projects in config.toml:
        [claude_server]
        default_project = "my-project"

        [claude_server.projects]
        my-project = "/path/to/project"
        dotfiles = "~/.dotfiles"

    Endpoints:
    - POST /prompt - Simple prompt with auto project management
    - GET /logs - View recent logs
    - GET /log/{id} - View log details
    - GET /projects - List configured projects
    - POST /switch-project - Switch current project
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

    # Load config for projects
    from agent_cli.config import load_config  # noqa: PLC0415

    config = load_config(config_file)
    claude_server_config = config.get("claude_server", {})
    projects = claude_server_config.get("projects", {})
    default_project = claude_server_config.get("default_project")

    # Default to current directory if not specified
    if cwd is None:
        cwd = Path.cwd()

    # If no projects configured, add cwd as default project
    if not projects:
        projects = {"default": str(cwd.resolve())}
        default_project = "default"

    console.print(
        f"[bold green]Starting Claude Code remote server on {host}:{port}[/bold green]",
    )
    console.print(f"[dim]Working directory: {cwd.resolve()}[/dim]")
    if projects:
        console.print(f"[dim]Projects: {', '.join(projects.keys())}[/dim]")
        if default_project:
            console.print(f"[dim]Default project: {default_project}[/dim]")
    console.print()
    console.print("[bold]Endpoints:[/bold]")
    console.print(f"  POST http://{host}:{port}/prompt")
    console.print(f"  GET  http://{host}:{port}/logs")
    console.print(f"  GET  http://{host}:{port}/projects")
    console.print()

    if reload:
        console.print("[yellow]Auto-reload enabled for development[/yellow]")

    run_claude_server(
        host=host,
        port=port,
        reload=reload,
        cwd=cwd,
        projects=projects,
        default_project=default_project,
    )
