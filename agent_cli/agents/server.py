"""FastAPI server command for Agent CLI."""

from __future__ import annotations

from importlib.util import find_spec

import typer

from agent_cli.cli import app
from agent_cli.core.utils import console, print_error_message

has_uvicorn = find_spec("uvicorn") is not None
has_fastapi = find_spec("fastapi") is not None


def run_server(
    host: str = "0.0.0.0",  # noqa: S104
    port: int = 61337,
    reload: bool = False,
) -> None:
    """Run the FastAPI server."""
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "agent_cli.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command("server")
def server(
    host: str = typer.Option("0.0.0.0", help="Host to bind the server to"),  # noqa: S104
    port: int = typer.Option(61337, help="Port to bind the server to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),  # noqa: FBT003
) -> None:
    """Run the FastAPI transcription web server."""
    if not has_uvicorn or not has_fastapi:
        msg = "uvicorn or fastapi is not installed, please install it with `pip install fastapi[standard]` or `pip install agent-cli[server]`"
        print_error_message(msg)
        raise typer.Exit(1)
    console.print(
        f"[bold green]Starting Agent CLI transcription server on {host}:{port}[/bold green]",
    )
    if reload:
        console.print("[yellow]Auto-reload enabled for development[/yellow]")
    run_server(host=host, port=port, reload=reload)
