"""Orchestration CLI commands for tracked agents (tmux-only)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from agent_cli.core.utils import console

from . import worktree
from ._output import error, info, success, warn
from .cli import app

if TYPE_CHECKING:
    from . import agent_state


def _ensure_git_repo() -> Path:
    """Ensure we're in a git repository and return the repo root."""
    if not worktree.git_available():
        error("Git is not installed or not in PATH")

    repo_root = worktree.get_main_repo_root()
    if repo_root is None:
        error("Not in a git repository")

    return repo_root


def _ensure_tmux() -> None:
    """Exit with an error if not running inside tmux."""
    from . import agent_state as _agent_state  # noqa: PLC0415

    if not _agent_state.is_tmux():
        error("Agent tracking requires tmux. Start a tmux session first.")


def _lookup_agent(name: str) -> tuple[Path, agent_state.TrackedAgent]:
    """Look up a tracked agent by name. Exits on error."""
    from . import agent_state as _agent_state  # noqa: PLC0415

    repo_root = _ensure_git_repo()
    state = _agent_state.load_state(repo_root)
    agent = state.agents.get(name)
    if agent is None:
        error(f"Agent '{name}' not found. Run 'dev poll' to see tracked agents.")
    return repo_root, agent


def _format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration."""
    if seconds < 60:  # noqa: PLR2004
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:  # noqa: PLR2004
        return f"{minutes}m {secs}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h {mins}m"


def _status_style(status: str) -> str:
    """Return a Rich-styled status string."""
    styles = {
        "running": "[bold green]running[/bold green]",
        "done": "[bold cyan]done[/bold cyan]",
        "quiet": "[bold cyan]quiet[/bold cyan]",
        "dead": "[bold red]dead[/bold red]",
    }
    return styles.get(status, status)


@app.command("poll", rich_help_panel="Agent Orchestration")
def poll_cmd(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Check status of all tracked agents.

    Performs a single poll of all tracked agents (checks tmux panes and
    completion sentinels) then displays results.

    **Status values:**

    - **running** — Agent pane exists and task is still in progress
    - **done** — Agent wrote a completion sentinel (.claude/DONE)
    - **quiet** — Agent output unchanged for several consecutive polls
    - **dead** — tmux pane no longer exists

    **Examples:**

    - `dev poll` — Show status table
    - `dev poll --json` — Machine-readable output
    """
    from . import agent_state as _agent_state  # noqa: PLC0415
    from .poller import poll_once  # noqa: PLC0415

    _ensure_tmux()
    repo_root = _ensure_git_repo()
    state = _agent_state.load_state(repo_root)

    if not state.agents:
        info("No tracked agents. Launch one with 'dev new -a' or 'dev agent --tab'.")
        return

    poll_once(repo_root)

    # Reload state after polling
    state = _agent_state.load_state(repo_root)
    now = time.time()

    if json_output:
        data = {
            "agents": [
                {
                    "name": a.name,
                    "status": a.status,
                    "agent_type": a.agent_type,
                    "worktree_path": a.worktree_path,
                    "pane_id": a.pane_id,
                    "started_at": a.started_at,
                    "duration_seconds": round(now - a.started_at),
                }
                for a in state.agents.values()
            ],
            "last_poll_at": state.last_poll_at,
        }
        print(json.dumps(data, indent=2))
        return

    from rich.table import Table  # noqa: PLC0415

    table = Table(title="Agent Status")
    table.add_column("Name", style="cyan")
    table.add_column("Status")
    table.add_column("Agent", style="dim")
    table.add_column("Worktree", style="dim")
    table.add_column("Duration", style="dim")

    for a in state.agents.values():
        table.add_row(
            a.name,
            _status_style(a.status),
            a.agent_type,
            Path(a.worktree_path).name,
            _format_duration(now - a.started_at),
        )

    console.print(table)

    # Summary line
    total = len(state.agents)
    by_status: dict[str, int] = {}
    for a in state.agents.values():
        by_status[a.status] = by_status.get(a.status, 0) + 1
    parts = [f"{total} agent{'s' if total != 1 else ''}"]
    parts.extend(
        f"{count} {status}"
        for status in ("running", "done", "quiet", "dead")
        if (count := by_status.get(status, 0))
    )
    console.print(f"\n[dim]{' · '.join(parts)}[/dim]")


@app.command("output", rich_help_panel="Agent Orchestration")
def output_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Agent name (from 'dev poll')"),
    ],
    lines: Annotated[
        int,
        typer.Option("--lines", "-n", help="Number of lines to capture"),
    ] = 50,
) -> None:
    """Get recent terminal output from a tracked agent.

    Captures the last N lines from the agent's tmux pane.

    **Examples:**

    - `dev output my-feature` — Last 50 lines
    - `dev output my-feature -n 200` — Last 200 lines
    """
    from . import tmux_ops  # noqa: PLC0415

    _ensure_tmux()
    _repo_root, agent = _lookup_agent(name)

    if agent.status == "dead":
        error(f"Agent '{name}' is dead (tmux pane closed). No output available.")

    output = tmux_ops.capture_pane(agent.pane_id, lines)
    if output is None:
        error(f"Could not capture output from pane {agent.pane_id}")
    print(output, end="")


@app.command("send", rich_help_panel="Agent Orchestration")
def send_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Agent name (from 'dev poll')"),
    ],
    message: Annotated[
        str,
        typer.Argument(help="Text to send to the agent's terminal"),
    ],
    no_enter: Annotated[
        bool,
        typer.Option("--no-enter", help="Don't press Enter after sending"),
    ] = False,
) -> None:
    """Send text input to a running agent's terminal.

    Types the message into the agent's tmux pane using ``tmux send-keys``.
    By default, presses Enter after the message.

    **Examples:**

    - `dev send my-feature "Fix the failing tests"` — Send a message
    - `dev send my-feature "/exit" --no-enter` — Send without pressing Enter
    """
    from . import tmux_ops  # noqa: PLC0415

    _ensure_tmux()
    _repo_root, agent = _lookup_agent(name)

    if agent.status == "dead":
        error(f"Agent '{name}' is dead (tmux pane closed). Cannot send messages.")

    if tmux_ops.send_keys(agent.pane_id, message, enter=not no_enter):
        success(f"Sent message to {name}")
    else:
        error(f"Failed to send message to pane {agent.pane_id}")


@app.command("wait", rich_help_panel="Agent Orchestration")
def wait_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Agent name (from 'dev poll')"),
    ],
    timeout: Annotated[
        float,
        typer.Option("--timeout", "-t", help="Timeout in seconds (0 = no timeout)"),
    ] = 0,
    interval: Annotated[
        float,
        typer.Option("--interval", "-i", help="Poll interval in seconds"),
    ] = 5.0,
) -> None:
    """Block until a tracked agent finishes.

    Polls the agent's tmux pane until it reaches done/dead, with output
    quiescence as a fallback for agents without completion sentinels.
    Useful for orchestration: launch an agent, wait for it, then act on results.

    **Exit codes:**

    - 0 — Agent finished (done or quiet fallback)
    - 1 — Agent died (pane closed unexpectedly)
    - 2 — Timeout reached

    **Examples:**

    - `dev wait my-feature` — Wait indefinitely
    - `dev wait my-feature --timeout 300` — Wait up to 5 minutes
    - `dev wait my-feature -i 2` — Poll every 2 seconds
    """
    from .poller import wait_for_agent  # noqa: PLC0415

    _ensure_tmux()
    repo_root, agent = _lookup_agent(name)

    if agent.status in ("done", "quiet", "dead"):
        console.print(f"Agent '{name}' is already {_status_style(agent.status)}")
        raise typer.Exit(0 if agent.status != "dead" else 1)

    info(f"Waiting for agent '{name}' to finish (polling every {interval}s)...")

    try:
        status, elapsed = wait_for_agent(repo_root, name, timeout=timeout, interval=interval)
    except TimeoutError:
        warn(f"Timeout after {_format_duration(timeout)}")
        raise typer.Exit(2) from None

    if status == "dead":
        warn(f"Agent '{name}' died (pane closed) after {_format_duration(elapsed)}")
        raise typer.Exit(1)

    if status == "quiet":
        success(
            f"Agent '{name}' appears quiet after {_format_duration(elapsed)} "
            "(no output changes detected)",
        )
    else:
        success(f"Agent '{name}' is {status} after {_format_duration(elapsed)}")
    raise typer.Exit(0)
