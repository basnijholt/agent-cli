"""Console output helpers for the dev module."""

from __future__ import annotations

from typing import NoReturn

import typer

from agent_cli.core.utils import console, err_console


def _error(msg: str) -> NoReturn:
    """Print an error message and exit."""
    err_console.print(f"[bold red]Error:[/bold red] {msg}")
    raise typer.Exit(1)


def _success(msg: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]✓[/bold green] {msg}")


def _info(msg: str) -> None:
    """Print an info message, with special styling for commands."""
    # Style commands (messages starting with "Running: ")
    if msg.startswith("Running: "):
        cmd = msg[9:]  # Remove "Running: " prefix
        # Escape brackets to prevent Rich from interpreting them as markup
        cmd = cmd.replace("[", r"\[")
        console.print(f"[dim]→[/dim] Running: [bold cyan]{cmd}[/bold cyan]")
    else:
        console.print(f"[dim]→[/dim] {msg}")


def _warn(msg: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]Warning:[/yellow] {msg}")
