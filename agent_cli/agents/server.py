"""FastAPI server command for Agent CLI."""

from __future__ import annotations

import typer

from agent_cli import opts
from agent_cli.cli import app
from agent_cli.core.utils import console


@app.command("server")
def server(
    host: str = typer.Option("0.0.0.0", help="Host to bind the server to"),  # noqa: S104
    port: int = typer.Option(61337, help="Port to bind the server to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),  # noqa: FBT003
    config_file: str | None = opts.CONFIG_FILE,  # noqa: ARG001
) -> None:
    """Run the FastAPI transcription web server."""
    from agent_cli.api import run_server  # noqa: PLC0415

    console.print(
        f"[bold green]Starting Agent CLI transcription server on {host}:{port}[/bold green]",
    )
    if reload:
        console.print("[yellow]Auto-reload enabled for development[/yellow]")

    run_server(host=host, port=port, reload=reload)
