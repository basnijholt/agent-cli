"""CLI commands for the space module."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING, Annotated, NoReturn

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent_cli.cli import set_config_defaults

from . import coding_agents, editors, terminals, worktree
from .project import copy_env_files, detect_project_type, run_setup

if TYPE_CHECKING:
    from pathlib import Path

    from .coding_agents.base import CodingAgent
    from .editors.base import Editor

console = Console()

app = typer.Typer(
    name="space",
    help="Parallel development environment manager using git worktrees.",
    add_completion=True,
    rich_markup_mode="markdown",
)


@app.callback()
def space_callback(
    ctx: typer.Context,
    config_file: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
) -> None:
    """Parallel development environment manager using git worktrees."""
    set_config_defaults(ctx, config_file)


def _error(msg: str) -> NoReturn:
    """Print an error message and exit."""
    console.print(f"[bold red]Error:[/bold red] {msg}")
    raise typer.Exit(1)


def _success(msg: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]✓[/bold green] {msg}")


def _info(msg: str) -> None:
    """Print an info message."""
    console.print(f"[dim]→[/dim] {msg}")


def _warn(msg: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]Warning:[/yellow] {msg}")


def _ensure_git_repo() -> Path:
    """Ensure we're in a git repository and return the repo root."""
    if not worktree.git_available():
        _error("Git is not installed or not in PATH")

    repo_root = worktree.get_main_repo_root()
    if repo_root is None:
        _error("Not in a git repository")

    return repo_root


def _resolve_editor(
    editor_flag: bool,
    editor_name: str | None,
    default_editor: str | None = None,
) -> Editor | None:
    """Resolve which editor to use based on flags and config defaults."""
    # Use explicit name if provided
    if editor_name:
        editor = editors.get_editor(editor_name)
        if editor is None:
            _warn(f"Editor '{editor_name}' not found")
        return editor

    # If no flag and no default, don't use an editor
    if not editor_flag and not default_editor:
        return None

    # If default is set in config, use it
    if default_editor:
        editor = editors.get_editor(default_editor)
        if editor is not None:
            return editor
        _warn(f"Default editor '{default_editor}' from config not found")

    # Auto-detect current or first available
    editor = editors.detect_current_editor()
    if editor is None:
        available = editors.get_available_editors()
        return available[0] if available else None
    return editor


def _resolve_agent(
    agent_flag: bool,
    agent_name: str | None,
    default_agent: str | None = None,
) -> CodingAgent | None:
    """Resolve which coding agent to use based on flags and config defaults."""
    # Use explicit name if provided
    if agent_name:
        agent = coding_agents.get_agent(agent_name)
        if agent is None:
            _warn(f"Agent '{agent_name}' not found")
        return agent

    # If no flag and no default, don't use an agent
    if not agent_flag and not default_agent:
        return None

    # If default is set in config, use it
    if default_agent:
        agent = coding_agents.get_agent(default_agent)
        if agent is not None:
            return agent
        _warn(f"Default agent '{default_agent}' from config not found")

    # Auto-detect current or first available
    agent = coding_agents.detect_current_agent()
    if agent is None:
        available = coding_agents.get_available_agents()
        return available[0] if available else None
    return agent


def _is_ssh_session() -> bool:
    """Check if we're in an SSH session."""
    return bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"))


def _launch_editor(path: Path, editor: Editor) -> None:
    """Launch editor via subprocess (editors are GUI apps that detach)."""
    try:
        subprocess.Popen(editor.open_command(path))
        _success(f"Opened {editor.name}")
    except Exception as e:
        _warn(f"Could not open editor: {e}")


def _launch_agent(path: Path, agent: CodingAgent) -> None:
    """Launch agent in a new terminal tab.

    Agents are interactive TUIs that need a proper terminal.
    Priority: tmux/zellij tab > terminal tab > print instructions.
    """
    terminal = terminals.detect_current_terminal()
    agent_cmd = " ".join(agent.launch_command(path))

    if terminal:
        # We're in a multiplexer (tmux/zellij) or supported terminal (kitty/iTerm2)
        if terminal.open_new_tab(path, agent_cmd):
            _success(f"Started {agent.name} in new {terminal.name} tab")
            return
        _warn(f"Could not open new tab in {terminal.name}")

    # No terminal detected or failed - print instructions
    if _is_ssh_session():
        console.print("\n[yellow]SSH session without terminal multiplexer.[/yellow]")
        console.print("[bold]Start a multiplexer first, then run:[/bold]")
    else:
        console.print(f"\n[bold]To start {agent.name}:[/bold]")
    console.print(f"  cd {path}")
    console.print(f"  {agent.command}")


@app.command("new")
def new(
    branch: Annotated[str, typer.Argument(help="Branch name for the new worktree")],
    from_ref: Annotated[
        str | None,
        typer.Option("--from", "-f", help="Create branch from this ref (default: main/master)"),
    ] = None,
    editor_flag: Annotated[
        bool,
        typer.Option("--editor", "-e", help="Open in editor after creation"),
    ] = False,
    agent_flag: Annotated[
        bool,
        typer.Option("--agent", "-a", help="Start AI coding agent after creation"),
    ] = False,
    agent_name: Annotated[
        str | None,
        typer.Option("--with-agent", help="Specific agent to use (claude, codex, gemini, aider)"),
    ] = None,
    editor_name: Annotated[
        str | None,
        typer.Option("--with-editor", help="Specific editor to use (cursor, vscode, zed)"),
    ] = None,
    default_agent: Annotated[
        str | None,
        typer.Option(hidden=True, help="Default agent from config"),
    ] = None,
    default_editor: Annotated[
        str | None,
        typer.Option(hidden=True, help="Default editor from config"),
    ] = None,
    no_setup: Annotated[
        bool,
        typer.Option("--no-setup", help="Skip automatic project setup"),
    ] = False,
    no_copy: Annotated[bool, typer.Option("--no-copy", help="Skip copying env files")] = False,
    no_fetch: Annotated[
        bool,
        typer.Option("--no-fetch", help="Skip git fetch before creating"),
    ] = False,
) -> None:
    """Create a new parallel development space (git worktree)."""
    repo_root = _ensure_git_repo()

    # Create the worktree
    _info(f"Creating worktree for branch '{branch}'...")
    result = worktree.create_worktree(
        branch,
        repo_path=repo_root,
        from_ref=from_ref,
        fetch=not no_fetch,
    )

    if not result.success:
        _error(result.error or "Failed to create worktree")

    assert result.path is not None
    _success(f"Created worktree at {result.path}")

    # Copy env files
    if not no_copy:
        copied = copy_env_files(repo_root, result.path)
        if copied:
            _info(f"Copied {len(copied)} env file(s)")

    # Detect and run project setup
    if not no_setup:
        project = detect_project_type(result.path)
        if project:
            _info(f"Detected {project.description}, running setup...")
            success, output = run_setup(result.path, project)
            if success:
                _success("Project setup complete")
            else:
                _warn(f"Setup failed: {output}")

    # Resolve editor and agent
    editor = _resolve_editor(editor_flag, editor_name, default_editor)
    agent = _resolve_agent(agent_flag, agent_name, default_agent)

    # Launch editor (GUI app - subprocess works)
    if editor and editor.is_available():
        _launch_editor(result.path, editor)

    # Launch agent (interactive TUI - needs terminal tab)
    if agent and agent.is_available():
        _launch_agent(result.path, agent)

    # Print summary
    console.print()
    console.print(
        Panel(
            f"[bold]Space created:[/bold] {result.path}\n[bold]Branch:[/bold] {result.branch}",
            title="[green]Success[/green]",
            border_style="green",
        ),
    )


@app.command("list")
def list_spaces(
    porcelain: Annotated[
        bool,
        typer.Option("--porcelain", "-p", help="Machine-readable output"),
    ] = False,
) -> None:
    """List all spaces (worktrees) for the current repository."""
    _ensure_git_repo()

    worktrees = worktree.list_worktrees()

    if not worktrees:
        console.print("[dim]No worktrees found[/dim]")
        return

    if porcelain:
        for wt in worktrees:
            print(f"{wt.path}\t{wt.branch or '(detached)'}")
        return

    table = Table(title="Spaces (Git Worktrees)")
    table.add_column("Name", style="cyan")
    table.add_column("Branch", style="green")
    table.add_column("Path", style="dim")
    table.add_column("Status", style="yellow")

    for wt in worktrees:
        name = "[bold]main[/bold]" if wt.is_main else wt.name
        branch_name = wt.branch or "(detached)"

        status_parts = []
        if wt.is_main:
            status_parts.append("main")
        if wt.is_detached:
            status_parts.append("detached")
        if wt.is_locked:
            status_parts.append("locked")
        if wt.is_prunable:
            status_parts.append("prunable")
        status = ", ".join(status_parts) if status_parts else "ok"

        table.add_row(name, branch_name, str(wt.path), status)

    console.print(table)


@app.command("rm")
def remove(
    name: Annotated[str, typer.Argument(help="Branch or directory name of the worktree to remove")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force removal even with uncommitted changes"),
    ] = False,
    delete_branch: Annotated[
        bool,
        typer.Option("--delete-branch", "-d", help="Also delete the branch"),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Remove a space (worktree)."""
    repo_root = _ensure_git_repo()

    wt = worktree.find_worktree_by_name(name, repo_root)
    if wt is None:
        _error(f"Worktree not found: {name}")

    if wt.is_main:
        _error("Cannot remove the main worktree")

    if not yes:
        console.print(f"[bold]Will remove:[/bold] {wt.path}")
        if delete_branch:
            console.print(f"[bold]Will delete branch:[/bold] {wt.branch}")
        if not typer.confirm("Continue?"):
            raise typer.Abort

    success, error = worktree.remove_worktree(
        wt.path,
        force=force,
        delete_branch=delete_branch,
        repo_path=repo_root,
    )

    if success:
        _success(f"Removed worktree: {wt.path}")
    else:
        _error(error or "Failed to remove worktree")


@app.command("go")
def go(
    name: Annotated[str, typer.Argument(help="Branch name or directory name of the worktree")],
) -> None:
    """Print the path to a space (for shell integration).

    Usage: cd "$(agent space go my-feature)"
    """
    repo_root = _ensure_git_repo()

    wt = worktree.find_worktree_by_name(name, repo_root)
    if wt is None:
        _error(f"Worktree not found: {name}")

    print(wt.path)


@app.command("editor")
def open_editor(
    name: Annotated[str, typer.Argument(help="Branch name or directory name of the worktree")],
    editor_name: Annotated[
        str | None,
        typer.Option("--editor", "-e", help="Specific editor to use"),
    ] = None,
) -> None:
    """Open a space in an editor."""
    repo_root = _ensure_git_repo()

    wt = worktree.find_worktree_by_name(name, repo_root)
    if wt is None:
        _error(f"Worktree not found: {name}")

    if editor_name:
        editor = editors.get_editor(editor_name)
        if editor is None:
            _error(f"Editor not found: {editor_name}")
    else:
        editor = editors.detect_current_editor()
        if editor is None:
            available = editors.get_available_editors()
            if not available:
                _error("No editors available")
            editor = available[0]

    if not editor.is_available():
        _error(f"{editor.name} is not installed")

    try:
        subprocess.Popen(editor.open_command(wt.path))
        _success(f"Opened {wt.path} in {editor.name}")
    except Exception as e:
        _error(f"Failed to open editor: {e}")


@app.command("agent")
def start_agent(
    name: Annotated[str, typer.Argument(help="Branch name or directory name of the worktree")],
    agent_name: Annotated[
        str | None,
        typer.Option("--agent", "-a", help="Specific agent (claude, codex, gemini, aider)"),
    ] = None,
) -> None:
    """Start an AI coding agent in a space."""
    repo_root = _ensure_git_repo()

    wt = worktree.find_worktree_by_name(name, repo_root)
    if wt is None:
        _error(f"Worktree not found: {name}")

    if agent_name:
        agent = coding_agents.get_agent(agent_name)
        if agent is None:
            _error(f"Agent not found: {agent_name}")
    else:
        agent = coding_agents.detect_current_agent()
        if agent is None:
            available = coding_agents.get_available_agents()
            if not available:
                _error("No AI coding agents available")
            agent = available[0]

    if not agent.is_available():
        _error(f"{agent.name} is not installed. Install from: {agent.install_url}")

    _info(f"Starting {agent.name} in {wt.path}...")
    try:
        os.chdir(wt.path)
        subprocess.run(agent.launch_command(wt.path), check=False)
    except Exception as e:
        _error(f"Failed to start agent: {e}")


@app.command("agents")
def list_agents() -> None:
    """List available AI coding agents."""
    current = coding_agents.detect_current_agent()

    table = Table(title="AI Coding Agents")
    table.add_column("Status", width=3)
    table.add_column("Name", style="cyan")
    table.add_column("Command", style="dim")
    table.add_column("Notes")

    for agent in coding_agents.get_all_agents():
        status = "[green]✓[/green]" if agent.is_available() else "[red]✗[/red]"
        notes = ""
        if current and agent.name == current.name:
            notes = "[bold yellow]← current[/bold yellow]"
        elif not agent.is_available():
            notes = f"[dim]{agent.install_url}[/dim]"
        table.add_row(status, agent.name, agent.command, notes)

    console.print(table)


@app.command("editors")
def list_editors_cmd() -> None:
    """List available editors."""
    current = editors.detect_current_editor()

    table = Table(title="Editors")
    table.add_column("Status", width=3)
    table.add_column("Name", style="cyan")
    table.add_column("Command", style="dim")
    table.add_column("Notes")

    for editor in editors.get_all_editors():
        status = "[green]✓[/green]" if editor.is_available() else "[red]✗[/red]"
        notes = ""
        if current and editor.name == current.name:
            notes = "[bold yellow]← current[/bold yellow]"
        elif not editor.is_available():
            notes = f"[dim]{editor.install_url}[/dim]"
        table.add_row(status, editor.name, editor.command, notes)

    console.print(table)


@app.command("terminals")
def list_terminals_cmd() -> None:
    """List available terminals."""
    current = terminals.detect_current_terminal()

    table = Table(title="Terminals")
    table.add_column("Status", width=3)
    table.add_column("Name", style="cyan")
    table.add_column("Notes")

    for terminal in terminals.get_all_terminals():
        status = "[green]✓[/green]" if terminal.is_available() else "[red]✗[/red]"
        notes = (
            "[bold yellow]← current[/bold yellow]"
            if current and terminal.name == current.name
            else ""
        )
        table.add_row(status, terminal.name, notes)

    console.print(table)


def _print_item_status(
    name: str,
    available: bool,
    is_current: bool,
    not_available_msg: str = "not installed",
) -> None:
    """Print status of an item (editor, agent, terminal)."""
    if available:
        note = " [yellow](current)[/yellow]" if is_current else ""
        _success(f"{name}{note}")
    else:
        console.print(f"  [dim]○[/dim] {name} ({not_available_msg})")


def _doctor_check_git() -> None:
    """Check git status for doctor command."""
    console.print("[bold]Git:[/bold]")
    if worktree.git_available():
        _success("Git is available")
    else:
        console.print("  [red]✗[/red] Git is not installed")

    repo_root = worktree.get_main_repo_root()
    if repo_root:
        _success(f"In git repository: {repo_root}")
    else:
        console.print("  [yellow]○[/yellow] Not in a git repository")


@app.command("doctor")
def doctor() -> None:
    """Check system requirements and available integrations."""
    console.print("[bold]Space Doctor[/bold]\n")

    _doctor_check_git()
    console.print()

    # Check editors
    console.print("[bold]Editors:[/bold]")
    current_editor = editors.detect_current_editor()
    for editor in editors.get_all_editors():
        is_current = current_editor is not None and editor.name == current_editor.name
        _print_item_status(editor.name, editor.is_available(), is_current)
    console.print()

    # Check agents
    console.print("[bold]AI Coding Agents:[/bold]")
    current_agent = coding_agents.detect_current_agent()
    for agent in coding_agents.get_all_agents():
        is_current = current_agent is not None and agent.name == current_agent.name
        _print_item_status(agent.name, agent.is_available(), is_current)
    console.print()

    # Check terminals
    console.print("[bold]Terminals:[/bold]")
    current_terminal = terminals.detect_current_terminal()
    for terminal in terminals.get_all_terminals():
        is_current = current_terminal is not None and terminal.name == current_terminal.name
        _print_item_status(terminal.name, terminal.is_available(), is_current, "not available")
