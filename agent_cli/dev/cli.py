"""CLI commands for the dev module."""

from __future__ import annotations

import json
import os
import random
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NoReturn

import typer
from rich.panel import Panel
from rich.table import Table

from agent_cli.cli import app as main_app
from agent_cli.cli import set_config_defaults
from agent_cli.config import load_config
from agent_cli.core.process import set_process_title
from agent_cli.core.utils import console, err_console

# Word lists for generating random branch names (like Docker container names)
_ADJECTIVES = [
    "happy",
    "clever",
    "swift",
    "bright",
    "calm",
    "eager",
    "fancy",
    "gentle",
    "jolly",
    "keen",
    "lively",
    "merry",
    "nice",
    "proud",
    "quick",
    "sharp",
    "smart",
    "sunny",
    "witty",
    "zesty",
    "bold",
    "cool",
    "fresh",
    "grand",
]
_NOUNS = [
    "fox",
    "owl",
    "bear",
    "wolf",
    "hawk",
    "lion",
    "tiger",
    "eagle",
    "falcon",
    "otter",
    "panda",
    "raven",
    "shark",
    "whale",
    "zebra",
    "bison",
    "crane",
    "dolphin",
    "gecko",
    "heron",
    "koala",
    "lemur",
    "moose",
    "newt",
    "oriole",
]


def _generate_branch_name(existing_branches: set[str] | None = None) -> str:
    """Generate a unique random branch name like 'clever-fox'.

    If the name already exists, adds a numeric suffix (clever-fox-2).
    """
    existing = existing_branches or set()
    base = f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}"  # noqa: S311

    if base not in existing:
        return base

    # Add numeric suffix to avoid collision
    for i in range(2, 100):
        candidate = f"{base}-{i}"
        if candidate not in existing:
            return candidate

    # Fallback: add random digits
    return f"{base}-{random.randint(100, 999)}"  # noqa: S311


from . import coding_agents, editors, terminals, worktree  # noqa: E402
from .project import (  # noqa: E402
    copy_env_files,
    detect_project_type,
    is_direnv_available,
    run_setup,
    setup_direnv,
)

if TYPE_CHECKING:
    from .coding_agents.base import CodingAgent
    from .editors.base import Editor

app = typer.Typer(
    name="dev",
    help="""Parallel development environment manager using git worktrees.

Creates isolated working directories for each feature branch, allowing you to
work on multiple features simultaneously without stashing changes. Each worktree
has its own branch and working directory.

**Common workflows:**

- `dev new feature-x -a` — Create worktree + start AI agent in new terminal tab
- `dev new feature-x -e -a` — Create worktree + open editor + start agent
- `dev new -a -p "Fix the auth bug"` — Create worktree + start agent with prompt
- `dev status` — See all worktrees with uncommitted changes
- `dev clean --merged` — Remove worktrees whose PRs are merged

**Automatic features:**

- Project setup (npm install, poetry install, uv sync, etc.)
- Environment file copying (.env, .env.local)
- Direnv setup (.envrc generation)
- Git submodules and LFS initialization
""",
    add_completion=True,
    rich_markup_mode="markdown",
    no_args_is_help=True,
)
main_app.add_typer(app, name="dev", rich_help_panel="Development")


@app.callback()
def dev_callback(
    ctx: typer.Context,
    config_file: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to config file"),
    ] = None,
) -> None:
    """Parallel development environment manager using git worktrees.

    Creates isolated working directories for each feature branch. Each worktree
    has its own branch, allowing parallel development without stashing changes.
    """
    set_config_defaults(ctx, config_file)
    if ctx.invoked_subcommand is not None:
        set_process_title(f"dev-{ctx.invoked_subcommand}")


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


def _ensure_git_repo() -> Path:
    """Ensure we're in a git repository and return the repo root."""
    if not worktree.git_available():
        _error("Git is not installed or not in PATH")

    repo_root = worktree.get_main_repo_root()
    if repo_root is None:
        _error("Not in a git repository")

    return repo_root


def _resolve_editor(
    use_editor: bool,
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
    if not use_editor and not default_editor:
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
    use_agent: bool,
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
    if not use_agent and not default_agent:
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


def _get_config_agent_args() -> dict[str, list[str]] | None:
    """Load agent_args from config file.

    Config format:
        [dev.agent_args]
        claude = ["--dangerously-skip-permissions"]

    Note: The config loader may flatten section names, so we check both
    nested structure and flattened 'dev.agent_args' key.
    """
    config = load_config(None)

    # First try the simple nested structure (for testing/mocks)
    dev_config = config.get("dev", {})
    if isinstance(dev_config, dict) and "agent_args" in dev_config:
        return dev_config["agent_args"]

    # Handle flattened key "dev.agent_args"
    return config.get("dev.agent_args")


def _get_config_agent_env() -> dict[str, dict[str, str]] | None:
    """Load agent_env from config file.

    Config format:
        [dev.agent_env]
        claude = { CLAUDE_CODE_USE_VERTEX = "1", ANTHROPIC_MODEL = "opus" }

    Note: The config loader flattens nested dicts, so keys like
    'dev.agent_env.claude' become top-level. We reconstruct the
    agent_env dict from these flattened keys.
    """
    config = load_config(None)

    # First try the simple nested structure (for testing/mocks)
    dev_config = config.get("dev", {})
    if isinstance(dev_config, dict) and "agent_env" in dev_config:
        return dev_config["agent_env"]

    # Handle flattened keys like "dev.agent_env.claude"
    prefix = "dev.agent_env."
    result: dict[str, dict[str, str]] = {}
    for key, value in config.items():
        if key.startswith(prefix) and isinstance(value, dict):
            agent_name = key[len(prefix) :]
            result[agent_name] = value

    return result if result else None


def _get_agent_env(agent: CodingAgent) -> dict[str, str]:
    """Get environment variables for an agent.

    Merges config env vars with agent's built-in env vars.
    Config env vars take precedence.
    """
    # Start with agent's built-in env vars
    env = agent.get_env().copy()

    # Add config env vars (these override built-in ones)
    config_env = _get_config_agent_env()
    if config_env and agent.name in config_env:
        env.update(config_env[agent.name])

    return env


def _merge_agent_args(
    agent: CodingAgent,
    cli_args: list[str] | None,
) -> list[str] | None:
    """Merge CLI args with config args for an agent.

    Config args are applied first, CLI args are appended (and can override).
    """
    config_args = _get_config_agent_args()
    result: list[str] = []

    # Add config args for this agent
    if config_args and agent.name in config_args:
        result.extend(config_args[agent.name])

    # Add CLI args (these override/extend config args)
    if cli_args:
        result.extend(cli_args)

    return result if result else None


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


def _write_prompt_to_worktree(worktree_path: Path, prompt: str) -> Path:
    """Write the prompt to .claude/TASK.md in the worktree.

    This makes the task description available to the spawned agent
    and provides a record of what was requested.
    """
    claude_dir = worktree_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    task_file = claude_dir / "TASK.md"
    task_file.write_text(prompt + "\n")
    return task_file


def _format_env_prefix(env: dict[str, str]) -> str:
    """Format environment variables as shell prefix.

    Returns a string like 'VAR1=value1 VAR2=value2 ' that can be
    prepended to a command.
    """
    if not env:
        return ""
    # Quote values that contain spaces or special characters
    parts = [f"{k}={shlex.quote(v)}" for k, v in sorted(env.items())]
    return " ".join(parts) + " "


def _generate_heredoc_delimiter() -> str:
    """Generate a unique heredoc delimiter using UUID."""
    import uuid  # noqa: PLC0415

    return f"PROMPT_{uuid.uuid4().hex[:12]}"


def _create_prompt_wrapper_script(
    worktree_path: Path,
    agent: CodingAgent,
    prompt: str,
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    """Create a wrapper script that launches the agent with the prompt.

    Uses a heredoc with quoted delimiter to avoid ALL shell interpretation
    of special characters ($, !, `, etc.) in the prompt content.

    Script is written to a temp directory to avoid polluting the worktree.
    """
    script_path = Path(tempfile.gettempdir()) / f"agent-cli-{worktree_path.name}.sh"
    delimiter = _generate_heredoc_delimiter()

    # Build the agent command without the prompt
    exe = agent.get_executable()
    if exe is None:
        msg = f"{agent.name} is not installed"
        raise RuntimeError(msg)

    cmd_parts = [shlex.quote(exe)]
    if extra_args:
        cmd_parts.extend(shlex.quote(arg) for arg in extra_args)

    agent_cmd = " ".join(cmd_parts)
    env_prefix = _format_env_prefix(env or {})

    # Create script with heredoc - quoted delimiter prevents all shell expansion
    script_content = f"""#!/usr/bin/env bash
# Auto-generated script to launch agent with prompt
# The heredoc with quoted delimiter (<<'{delimiter}') prevents shell interpretation
{env_prefix}exec {agent_cmd} "$(cat <<'{delimiter}'
{prompt}
{delimiter}
)"
"""
    script_path.write_text(script_content)
    script_path.chmod(0o755)
    return script_path


def _launch_agent(
    path: Path,
    agent: CodingAgent,
    extra_args: list[str] | None = None,
    prompt: str | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Launch agent in a new terminal tab.

    Agents are interactive TUIs that need a proper terminal.
    Priority: tmux/zellij tab > terminal tab > print instructions.

    Args:
        path: Directory to launch the agent in
        agent: The coding agent to launch
        extra_args: Additional CLI arguments for the agent
        prompt: Optional initial prompt
        env: Environment variables to set for the agent

    """
    terminal = terminals.detect_current_terminal()

    # Use wrapper script for prompts when opening in a terminal tab.
    # All terminals pass commands through a shell (zellij write-chars, tmux new-window,
    # bash -c, AppleScript, etc.), so special characters ($, !, `, etc.) get interpreted.
    # The wrapper script uses a heredoc with quoted delimiter to prevent this.
    if prompt and terminal is not None:
        script_path = _create_prompt_wrapper_script(path, agent, prompt, extra_args, env)
        full_cmd = f"bash {shlex.quote(str(script_path))}"
    else:
        agent_cmd = shlex.join(agent.launch_command(path, extra_args, prompt))
        env_prefix = _format_env_prefix(env or {})
        full_cmd = env_prefix + agent_cmd

    if terminal:
        # We're in a multiplexer (tmux/zellij) or supported terminal (kitty/iTerm2)
        # Tab name format: repo@branch
        repo_root = worktree.get_main_repo_root(path)
        branch = worktree.get_current_branch(path)
        repo_name = repo_root.name if repo_root else path.name
        tab_name = f"{repo_name}@{branch}" if branch else repo_name
        if terminal.open_new_tab(path, full_cmd, tab_name=tab_name):
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
    console.print(f"  {full_cmd}")


@app.command("new")
def new(  # noqa: C901, PLR0912, PLR0915
    branch: Annotated[
        str | None,
        typer.Argument(
            help="Branch name for the worktree. If omitted, generates a random name like 'clever-fox'",
        ),
    ] = None,
    from_ref: Annotated[
        str | None,
        typer.Option(
            "--from",
            "-f",
            help="Git ref (branch/tag/commit) to branch from. Defaults to origin/main or origin/master",
        ),
    ] = None,
    editor: Annotated[
        bool,
        typer.Option(
            "--editor",
            "-e",
            help="Open the worktree in an editor. Uses --with-editor, config default, or auto-detects",
        ),
    ] = False,
    agent: Annotated[
        bool,
        typer.Option(
            "--agent",
            "-a",
            help="Start an AI coding agent in a new terminal tab. Uses --with-agent, config default, or auto-detects. Implied by --prompt",
        ),
    ] = False,
    agent_name: Annotated[
        str | None,
        typer.Option(
            "--with-agent",
            help="Which AI agent to start: claude, codex, gemini, aider, copilot, cn (Continue), opencode, cursor-agent",
        ),
    ] = None,
    editor_name: Annotated[
        str | None,
        typer.Option(
            "--with-editor",
            help="Which editor to open: cursor, vscode, zed, nvim, vim, emacs, sublime, idea, pycharm, etc.",
        ),
    ] = None,
    default_agent: Annotated[
        str | None,
        typer.Option(hidden=True, help="Default agent from config"),
    ] = None,
    default_editor: Annotated[
        str | None,
        typer.Option(hidden=True, help="Default editor from config"),
    ] = None,
    setup: Annotated[
        bool,
        typer.Option(
            "--setup/--no-setup",
            help="Run project setup after creation: npm/pnpm/yarn install, poetry/uv sync, cargo build, etc. Auto-detects project type",
        ),
    ] = True,
    copy_env: Annotated[
        bool,
        typer.Option(
            "--copy-env/--no-copy-env",
            help="Copy .env, .env.local, .env.example from main repo to worktree",
        ),
    ] = True,
    fetch: Annotated[
        bool,
        typer.Option(
            "--fetch/--no-fetch",
            help="Run 'git fetch' before creating the worktree to ensure refs are up-to-date",
        ),
    ] = True,
    direnv: Annotated[
        bool | None,
        typer.Option(
            "--direnv/--no-direnv",
            help="Generate .envrc based on project type and run 'direnv allow'. Auto-enabled if direnv is installed",
        ),
    ] = None,
    agent_args: Annotated[
        list[str] | None,
        typer.Option(
            "--agent-args",
            help="Extra CLI args for the agent. Can be repeated. Example: --agent-args='--dangerously-skip-permissions'",
        ),
    ] = None,
    prompt: Annotated[
        str | None,
        typer.Option(
            "--prompt",
            "-p",
            help="Initial task for the AI agent. Saved to .claude/TASK.md. Implies --agent. Example: --prompt='Fix the login bug'",
        ),
    ] = None,
    prompt_file: Annotated[
        Path | None,
        typer.Option(
            "--prompt-file",
            "-P",
            help="Read the agent prompt from a file. Useful for long prompts to avoid shell quoting. Implies --agent",
            exists=True,
            readable=True,
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Stream output from setup commands instead of hiding it",
        ),
    ] = False,
) -> None:
    """Create a new parallel development environment (git worktree).

    Creates an isolated git worktree with its own branch and working directory.
    Optionally runs project setup, opens an editor, and/or starts an AI agent.

    **What happens:**

    1. Creates git worktree at `../REPO-worktrees/BRANCH/`
    2. Copies .env files from main repo (--copy-env)
    3. Runs project setup: npm install, uv sync, etc. (--setup)
    4. Sets up direnv if installed (--direnv)
    5. Opens editor if requested (-e/--editor)
    6. Starts AI agent in new terminal tab if requested (-a/--agent or --prompt)

    **Examples:**

    - `dev new feature-x` — Create worktree, branching from origin/main (default)
    - `dev new feature-x -a` — Create + start Claude/detected agent
    - `dev new feature-x -e -a` — Create + open editor + start agent
    - `dev new -a --prompt "Fix auth bug"` — Auto-named branch + agent with task
    - `dev new hotfix --from v1.2.3` — Branch from a tag instead of main
    - `dev new feature-x --from origin/develop` — Branch from develop instead
    - `dev new feature-x --with-agent aider --with-editor cursor` — Specific tools
    """
    # Handle prompt-file option (takes precedence over --prompt)
    if prompt_file is not None:
        prompt = prompt_file.read_text().strip()

    # If a prompt is provided, automatically enable agent mode
    if prompt:
        agent = True

    repo_root = _ensure_git_repo()

    # Generate branch name if not provided
    if branch is None:
        # Get existing branches to avoid collisions
        existing = {wt.branch for wt in worktree.list_worktrees() if wt.branch}
        branch = _generate_branch_name(existing)
        _info(f"Generated branch name: {branch}")

    # Create the worktree
    _info(f"Creating worktree for branch '{branch}'...")
    result = worktree.create_worktree(
        branch,
        repo_path=repo_root,
        from_ref=from_ref,
        fetch=fetch,
        on_log=_info,
        capture_output=not verbose,
    )

    if not result.success:
        _error(result.error or "Failed to create worktree")

    assert result.path is not None
    _success(f"Created worktree at {result.path}")

    # Show warning if --from was ignored
    if result.warning:
        _warn(result.warning)

    # Copy env files
    if copy_env:
        copied = copy_env_files(repo_root, result.path)
        if copied:
            names = ", ".join(f.name for f in copied)
            _success(f"Copied env file(s): {names}")

    # Detect and run project setup
    project = None
    if setup:
        project = detect_project_type(result.path)
        if project:
            _info(f"Detected {project.description}")
            success, output = run_setup(
                result.path,
                project,
                on_log=_info,
                capture_output=not verbose,
            )
            if success:
                _success("Project setup complete")
            else:
                _warn(f"Setup failed: {output}")

    # Set up direnv (default: enabled if direnv is installed)
    use_direnv = direnv if direnv is not None else is_direnv_available()
    if use_direnv:
        if is_direnv_available():
            success, msg = setup_direnv(
                result.path,
                project,
                on_log=_info,
                capture_output=not verbose,
            )
            # Show success for meaningful actions (created or allowed)
            if success and ("created" in msg or "allowed" in msg):
                _success(msg)
            elif success:
                _info(msg)
            else:
                _warn(msg)
        elif direnv is True:
            # Only warn if user explicitly requested direnv
            _warn("direnv not installed, skipping .envrc setup")

    # Write prompt to worktree (makes task available to the spawned agent)
    if prompt:
        task_file = _write_prompt_to_worktree(result.path, prompt)
        _success(f"Wrote task to {task_file.relative_to(result.path)}")

    # Resolve editor and agent
    resolved_editor = _resolve_editor(editor, editor_name, default_editor)
    resolved_agent = _resolve_agent(agent, agent_name, default_agent)

    # Launch editor (GUI app - subprocess works)
    if resolved_editor and resolved_editor.is_available():
        _launch_editor(result.path, resolved_editor)

    # Launch agent (interactive TUI - needs terminal tab)
    if resolved_agent and resolved_agent.is_available():
        merged_args = _merge_agent_args(resolved_agent, agent_args)
        agent_env = _get_agent_env(resolved_agent)
        _launch_agent(result.path, resolved_agent, merged_args, prompt, agent_env)

    # Print summary
    console.print()
    console.print(
        Panel(
            f"[bold]Dev environment created:[/bold] {result.path}\n[bold]Branch:[/bold] {result.branch}",
            title="[green]Success[/green]",
            border_style="green",
        ),
    )
    console.print(f'[dim]To enter the worktree:[/dim] cd "$(ag dev path {branch})"')


@app.command("list")
def list_envs(
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON. Fields: name, path, branch, is_main, is_detached, is_locked, is_prunable",
        ),
    ] = False,
) -> None:
    """List all dev environments (worktrees) for the current repository.

    Shows each worktree's name, branch, path, and status (main, detached, locked, prunable).
    Use `dev status` for more details including uncommitted changes and commit history.
    """
    _ensure_git_repo()

    worktrees = worktree.list_worktrees()

    if not worktrees:
        if json_output:
            print(json.dumps({"worktrees": []}))
        else:
            console.print("[dim]No worktrees found[/dim]")
        return

    if json_output:
        data = [
            {
                "name": wt.name,
                "path": wt.path.as_posix(),
                "branch": wt.branch,
                "is_main": wt.is_main,
                "is_detached": wt.is_detached,
                "is_locked": wt.is_locked,
                "is_prunable": wt.is_prunable,
            }
            for wt in worktrees
        ]
        print(json.dumps({"worktrees": data}))
        return

    table = Table(title="Dev Environments (Git Worktrees)")
    table.add_column("Name", style="cyan")
    table.add_column("Branch", style="green")
    table.add_column("Path", style="dim", overflow="fold")
    table.add_column("Status", style="yellow")

    home = Path.home()

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

        # Use ~ for home directory to shorten paths
        try:
            display_path = "~/" + str(wt.path.relative_to(home))
        except ValueError:
            display_path = str(wt.path)

        table.add_row(name, branch_name, display_path, status)

    console.print(table)


def _format_file_changes(status: worktree.WorktreeStatus) -> str:
    """Format file changes for display (e.g., '2M 1S 3?')."""
    parts: list[str] = []
    if status.modified:
        parts.append(f"{status.modified}M")
    if status.staged:
        parts.append(f"{status.staged}S")
    if status.untracked:
        parts.append(f"{status.untracked}?")
    return " ".join(parts) if parts else "[dim]clean[/dim]"


def _format_ahead_behind(status: worktree.WorktreeStatus) -> str:
    """Format ahead/behind for display (e.g., '+3/-2')."""
    if status.ahead == 0 and status.behind == 0:
        return "[dim]—[/dim]"
    parts: list[str] = []
    if status.ahead:
        parts.append(f"[green]+{status.ahead}[/green]")
    if status.behind:
        parts.append(f"[red]-{status.behind}[/red]")
    return "/".join(parts)


def _is_stale(status: worktree.WorktreeStatus, stale_days: int) -> bool:
    """Check if worktree is stale based on last commit time."""
    import time  # noqa: PLC0415

    if status.last_commit_timestamp is None:
        return False
    days_since = (time.time() - status.last_commit_timestamp) / (60 * 60 * 24)
    return days_since >= stale_days


@app.command("status")
def status_cmd(  # noqa: PLR0915
    stale_days: Annotated[
        int,
        typer.Option(
            "--stale-days",
            "-s",
            help="Mark worktrees as stale if inactive for N+ days (default: 7)",
        ),
    ] = 7,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON with fields: name, branch, modified, staged, untracked, ahead, behind, last_commit_timestamp, is_stale",
        ),
    ] = False,
) -> None:
    """Show detailed status of all dev environments with git information.

    Displays for each worktree:
    - **Changes**: Modified (M), Staged (S), Untracked (?) file counts
    - **↑/↓**: Commits ahead (+N) or behind (-N) upstream
    - **Last Commit**: Time since last commit, with ⚠️ for stale worktrees

    Use this to find worktrees with uncommitted work or that need cleanup.
    """
    _ensure_git_repo()

    worktrees = worktree.list_worktrees()

    if not worktrees:
        if json_output:
            print(json.dumps({"worktrees": []}))
        else:
            console.print("[dim]No worktrees found[/dim]")
        return

    if json_output:
        data = []
        for wt in worktrees:
            status = worktree.get_worktree_status(wt.path)
            entry: dict[str, str | int | bool | float | None] = {
                "name": wt.name,
                "branch": wt.branch,
                "is_main": wt.is_main,
            }
            if status:
                entry["modified"] = status.modified
                entry["staged"] = status.staged
                entry["untracked"] = status.untracked
                entry["ahead"] = status.ahead
                entry["behind"] = status.behind
                entry["last_commit_timestamp"] = status.last_commit_timestamp
                entry["last_commit_time"] = status.last_commit_time
                entry["is_stale"] = _is_stale(status, stale_days)
            data.append(entry)
        print(json.dumps({"worktrees": data, "stale_days": stale_days}))
        return

    table = Table(title="Dev Environment Status")
    table.add_column("Name", style="cyan")
    table.add_column("Branch", style="green")
    table.add_column("Changes", justify="right")
    table.add_column("↑/↓", justify="center")
    table.add_column("Last Commit")

    for wt in worktrees:
        name = "[bold]main[/bold]" if wt.is_main else wt.name
        branch_name = wt.branch or "(detached)"

        status = worktree.get_worktree_status(wt.path)
        if status is None:
            table.add_row(name, branch_name, "[red]?[/red]", "", "")
            continue

        changes = _format_file_changes(status)
        ahead_behind = _format_ahead_behind(status)

        # Format last commit time with stale warning
        last_commit = status.last_commit_time or "[dim]unknown[/dim]"
        if _is_stale(status, stale_days):
            last_commit = f"[yellow]{last_commit} ⚠️[/yellow]"

        table.add_row(name, branch_name, changes, ahead_behind, last_commit)

    console.print(table)

    # Summary
    total = len(worktrees)
    stale_count = sum(
        1
        for wt in worktrees
        if (s := worktree.get_worktree_status(wt.path)) and _is_stale(s, stale_days)
    )
    dirty_count = sum(
        1
        for wt in worktrees
        if (s := worktree.get_worktree_status(wt.path))
        and (s.modified > 0 or s.staged > 0 or s.untracked > 0)
    )

    summary_parts = [f"[bold]{total}[/bold] worktree{'s' if total != 1 else ''}"]
    if dirty_count:
        summary_parts.append(f"[yellow]{dirty_count} with uncommitted changes[/yellow]")
    if stale_count:
        summary_parts.append(f"[yellow]{stale_count} stale (>{stale_days} days)[/yellow]")

    console.print("\n" + " · ".join(summary_parts))


@app.command("rm")
def remove(
    name: Annotated[
        str,
        typer.Argument(help="Worktree to remove. Can be branch name or directory name"),
    ],
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force removal even if worktree has uncommitted changes",
        ),
    ] = False,
    delete_branch: Annotated[
        bool,
        typer.Option(
            "--delete-branch",
            "-d",
            help="Also delete the git branch (not just the worktree)",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Remove a dev environment (worktree) and optionally its branch.

    By default, prompts for confirmation and refuses to remove worktrees with
    uncommitted changes. Use --force to override, --delete-branch to also
    delete the git branch.

    Cannot remove the main worktree.
    """
    repo_root = _ensure_git_repo()

    wt = worktree.find_worktree_by_name(name, repo_root)
    if wt is None:
        _error(f"Worktree not found: {name}")

    if wt.is_main:
        _error("Cannot remove the main worktree")

    if not yes and not force:
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


@app.command("path")
def path_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Worktree to get path for. Can be branch name or directory name"),
    ],
) -> None:
    """Print the absolute path to a dev environment.

    Useful for shell integration and scripting.

    **Example:** `cd "$(agent-cli dev path my-feature)"`
    """
    repo_root = _ensure_git_repo()

    wt = worktree.find_worktree_by_name(name, repo_root)
    if wt is None:
        _error(f"Worktree not found: {name}")

    print(wt.path.as_posix())


@app.command("editor")
def open_editor(
    name: Annotated[
        str,
        typer.Argument(help="Worktree to open. Can be branch name or directory name"),
    ],
    editor_name: Annotated[
        str | None,
        typer.Option(
            "--editor",
            "-e",
            help="Override auto-detection. Options: cursor, vscode, zed, nvim, vim, emacs, sublime, idea, pycharm, etc.",
        ),
    ] = None,
) -> None:
    """Open a dev environment in an editor.

    Without --editor, auto-detects based on current environment or uses
    the first available editor. Run `dev editors` to see what's available.
    """
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
    name: Annotated[
        str,
        typer.Argument(
            help="Worktree to start the agent in. Can be branch name or directory name",
        ),
    ],
    agent_name: Annotated[
        str | None,
        typer.Option(
            "--agent",
            "-a",
            help="Which agent: claude, codex, gemini, aider, copilot, cn, opencode, cursor-agent. Auto-detects if omitted",
        ),
    ] = None,
    agent_args: Annotated[
        list[str] | None,
        typer.Option(
            "--agent-args",
            help="Extra CLI args for the agent. Example: --agent-args='--dangerously-skip-permissions'",
        ),
    ] = None,
    prompt: Annotated[
        str | None,
        typer.Option(
            "--prompt",
            "-p",
            help="Initial task for the agent. Saved to .claude/TASK.md. Example: --prompt='Add unit tests for auth'",
        ),
    ] = None,
    prompt_file: Annotated[
        Path | None,
        typer.Option(
            "--prompt-file",
            "-P",
            help="Read the agent prompt from a file instead of command line",
            exists=True,
            readable=True,
        ),
    ] = None,
) -> None:
    """Start an AI coding agent in an existing dev environment.

    Launches the agent directly in your current terminal (not a new tab).
    Use this when the worktree already exists and you want to start/resume work.

    **Examples:**

    - `dev agent my-feature` — Start auto-detected agent in worktree
    - `dev agent my-feature -a claude` — Start Claude specifically
    - `dev agent my-feature -p "Continue the auth refactor"` — Start with a task
    """
    # Handle prompt-file option (takes precedence over --prompt)
    if prompt_file is not None:
        prompt = prompt_file.read_text().strip()

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

    # Write prompt to worktree (makes task available to the agent)
    if prompt:
        task_file = _write_prompt_to_worktree(wt.path, prompt)
        _success(f"Wrote task to {task_file.relative_to(wt.path)}")

    merged_args = _merge_agent_args(agent, agent_args)
    agent_env = _get_agent_env(agent)
    _info(f"Starting {agent.name} in {wt.path}...")
    try:
        os.chdir(wt.path)
        # Merge agent env with current environment
        run_env = os.environ.copy()
        run_env.update(agent_env)
        subprocess.run(
            agent.launch_command(wt.path, merged_args, prompt),
            check=False,
            env=run_env,
        )
    except Exception as e:
        _error(f"Failed to start agent: {e}")


@app.command("agents")
def list_agents(
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON with name, command, is_available, is_current, install_url",
        ),
    ] = False,
) -> None:
    """List available AI coding agents and their installation status.

    Shows all supported agents: claude, codex, gemini, aider, copilot,
    cn (Continue), opencode, cursor-agent.

    ✓ = installed, ✗ = not installed (shows install URL).
    Current agent (detected from parent process) is marked.
    """
    current = coding_agents.detect_current_agent()

    if json_output:
        data = [
            {
                "name": agent.name,
                "command": agent.command,
                "is_available": agent.is_available(),
                "is_current": current is not None and agent.name == current.name,
                "install_url": agent.install_url,
            }
            for agent in coding_agents.get_all_agents()
        ]
        print(json.dumps({"agents": data}))
        return

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
def list_editors_cmd(
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON with name, command, is_available, is_current, install_url",
        ),
    ] = False,
) -> None:
    """List available editors and their installation status.

    Shows all supported editors: cursor, vscode, zed, nvim, vim, emacs,
    sublime, idea, pycharm, webstorm, goland, rustrover.

    ✓ = installed, ✗ = not installed.
    Current editor (if detectable) is marked.
    """
    current = editors.detect_current_editor()

    if json_output:
        data = [
            {
                "name": editor.name,
                "command": editor.command,
                "is_available": editor.is_available(),
                "is_current": current is not None and editor.name == current.name,
                "install_url": editor.install_url,
            }
            for editor in editors.get_all_editors()
        ]
        print(json.dumps({"editors": data}))
        return

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
def list_terminals_cmd(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON with name, is_available, is_current"),
    ] = False,
) -> None:
    """List available terminal multiplexers and their status.

    Shows supported terminals: tmux, zellij, kitty, iTerm2, Terminal.app,
    Warp, GNOME Terminal.

    These are used to open new tabs when launching AI agents with `dev new -a`.
    The current terminal (if detectable) is marked.
    """
    current = terminals.detect_current_terminal()

    if json_output:
        data = [
            {
                "name": terminal.name,
                "is_available": terminal.is_available(),
                "is_current": current is not None and terminal.name == current.name,
            }
            for terminal in terminals.get_all_terminals()
        ]
        print(json.dumps({"terminals": data}))
        return

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


@app.command("run")
def run_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Worktree to run command in. Can be branch name or directory name"),
    ],
    command: Annotated[
        list[str],
        typer.Argument(help="Command and arguments to run"),
    ],
) -> None:
    """Run a command in a dev environment's directory.

    Executes the command with the worktree as the current directory.
    Exit code is passed through from the command.

    **Examples:**

    - `dev run my-feature npm test` — Run tests
    - `dev run my-feature git status` — Check git status
    - `dev run my-feature bash -c "npm install && npm test"` — Multiple commands
    """
    repo_root = _ensure_git_repo()

    wt = worktree.find_worktree_by_name(name, repo_root)
    if wt is None:
        _error(f"Worktree not found: {name}")

    if not command:
        _error("No command specified")

    _info(f"Running in {wt.path}: {' '.join(command)}")
    try:
        result = subprocess.run(command, cwd=wt.path, check=False)
        raise typer.Exit(result.returncode)
    except FileNotFoundError:
        _error(f"Command not found: {command[0]}")


def _find_worktrees_with_no_commits(repo_root: Path) -> list[worktree.WorktreeInfo]:
    """Find worktrees whose branches have no commits ahead of the default branch."""
    worktrees_list = worktree.list_worktrees()
    default_branch = worktree.get_default_branch(repo_root)
    to_remove: list[worktree.WorktreeInfo] = []

    for wt in worktrees_list:
        if wt.is_main or not wt.branch:
            continue

        # Check if branch has any commits ahead of default branch
        result = subprocess.run(
            ["git", "rev-list", f"{default_branch}..{wt.branch}", "--count"],  # noqa: S607
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip() == "0":
            to_remove.append(wt)

    return to_remove


def _find_worktrees_with_merged_prs(
    repo_root: Path,
) -> list[tuple[worktree.WorktreeInfo, str]]:
    """Find worktrees whose PRs have been merged on GitHub.

    Returns a list of tuples containing (worktree_info, pr_url).
    """
    worktrees_list = worktree.list_worktrees()
    to_remove: list[tuple[worktree.WorktreeInfo, str]] = []

    for wt in worktrees_list:
        if wt.is_main or not wt.branch:
            continue

        # Check if PR for this branch is merged
        result = subprocess.run(
            ["gh", "pr", "list", "--head", wt.branch, "--state", "merged", "--json", "number,url"],  # noqa: S607
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip() not in ("", "[]"):
            prs = json.loads(result.stdout)
            pr_url = prs[0]["url"] if prs else ""
            to_remove.append((wt, pr_url))

    return to_remove


def _clean_merged_worktrees(
    repo_root: Path,
    dry_run: bool,
    yes: bool,
) -> None:
    """Remove worktrees with merged PRs (requires gh CLI)."""
    _info("Checking for worktrees with merged PRs...")

    # Check if gh CLI is available
    gh_version = subprocess.run(
        ["gh", "--version"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if gh_version.returncode != 0:
        _error("GitHub CLI (gh) not found. Install from: https://cli.github.com/")

    # Check if gh is authenticated
    gh_auth = subprocess.run(
        ["gh", "auth", "status"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if gh_auth.returncode != 0:
        _error("Not authenticated with GitHub. Run: gh auth login")

    to_remove = _find_worktrees_with_merged_prs(repo_root)

    if not to_remove:
        _info("No worktrees with merged PRs found")
        return

    console.print(f"\n[bold]Found {len(to_remove)} worktree(s) with merged PRs:[/bold]")
    for wt, pr_url in to_remove:
        console.print(f"  • {wt.branch} ({wt.path})")
        if pr_url:
            console.print(f"    PR: [link={pr_url}]{pr_url}[/link]")

    if dry_run:
        _info("[dry-run] Would remove the above worktrees")
    elif yes or typer.confirm("\nRemove these worktrees?"):
        for wt, _pr_url in to_remove:
            success, error = worktree.remove_worktree(
                wt.path,
                force=False,
                delete_branch=True,
                repo_path=repo_root,
            )
            if success:
                _success(f"Removed {wt.branch}")
            else:
                _warn(f"Failed to remove {wt.branch}: {error}")


def _clean_no_commits_worktrees(
    repo_root: Path,
    dry_run: bool,
    yes: bool,
) -> None:
    """Remove worktrees with no commits ahead of the default branch."""
    _info("Checking for worktrees with no commits...")

    to_remove = _find_worktrees_with_no_commits(repo_root)

    if not to_remove:
        _info("No worktrees with zero commits found")
        return

    default_branch = worktree.get_default_branch(repo_root)
    console.print(
        f"\n[bold]Found {len(to_remove)} worktree(s) with no commits ahead of {default_branch}:[/bold]",
    )
    for wt in to_remove:
        console.print(f"  • {wt.branch} ({wt.path})")

    if dry_run:
        _info("[dry-run] Would remove the above worktrees")
    elif yes or typer.confirm("\nRemove these worktrees?"):
        for wt in to_remove:
            success, error = worktree.remove_worktree(
                wt.path,
                force=False,
                delete_branch=True,
                repo_path=repo_root,
            )
            if success:
                _success(f"Removed {wt.branch}")
            else:
                _warn(f"Failed to remove {wt.branch}: {error}")


@app.command("clean")
def clean(
    merged: Annotated[
        bool,
        typer.Option(
            "--merged",
            help="Also remove worktrees whose GitHub PRs are merged (requires gh CLI and auth)",
        ),
    ] = False,
    no_commits: Annotated[
        bool,
        typer.Option(
            "--no-commits",
            help="Also remove worktrees with 0 commits ahead of default branch (abandoned branches)",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Preview what would be removed without actually removing",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts"),
    ] = False,
) -> None:
    """Clean up stale worktrees and empty directories.

    Always runs `git worktree prune` to remove stale administrative files,
    and removes empty directories in the worktrees folder.

    **Modes:**

    - Default: Just prune stale refs and empty directories
    - `--merged`: Also remove worktrees whose PRs are merged on GitHub
    - `--no-commits`: Also remove worktrees with no commits (abandoned branches)

    **Examples:**

    - `dev clean` — Basic cleanup
    - `dev clean --merged` — Remove worktrees with merged PRs
    - `dev clean --merged --dry-run` — Preview what would be removed
    """
    repo_root = _ensure_git_repo()

    # Run git worktree prune
    _info("Pruning stale worktree references...")
    result = subprocess.run(
        ["git", "worktree", "prune"],  # noqa: S607
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        _success("Pruned stale worktree administrative files")
    else:
        _warn(f"Prune failed: {result.stderr}")

    # Find and remove empty directories in worktrees base dir
    base_dir = worktree.resolve_worktree_base_dir(repo_root)
    if base_dir and base_dir.exists():
        cleaned = 0
        for item in base_dir.iterdir():
            if item.is_dir() and not any(item.iterdir()):
                if dry_run:
                    _info(f"[dry-run] Would remove empty directory: {item.name}")
                else:
                    item.rmdir()
                    _info(f"Removed empty directory: {item.name}")
                cleaned += 1
        if cleaned > 0:
            _success(f"Cleaned {cleaned} empty director{'y' if cleaned == 1 else 'ies'}")

    # --merged mode: remove worktrees with merged PRs
    if merged:
        _clean_merged_worktrees(repo_root, dry_run, yes)

    # --no-commits mode: remove worktrees with no commits ahead of default branch
    if no_commits:
        _clean_no_commits_worktrees(repo_root, dry_run, yes)


@app.command("doctor")
def doctor(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON with git, editors, agents, terminals status"),
    ] = False,
) -> None:
    """Check system requirements and show available integrations.

    Shows availability status for:
    - **Git**: Is git installed? Are we in a git repo?
    - **Editors**: Which editors are installed and which is current?
    - **Agents**: Which AI coding agents are installed?
    - **Terminals**: Which terminal multiplexers are detected?

    Items marked with ✓ are available, ✗ are not installed.
    Current editor/agent/terminal is marked with (current).
    """
    current_editor = editors.detect_current_editor()
    current_agent = coding_agents.detect_current_agent()
    current_terminal = terminals.detect_current_terminal()

    if json_output:
        repo_root = worktree.get_main_repo_root()
        data = {
            "git": {
                "is_available": worktree.git_available(),
                "repo_root": repo_root.as_posix() if repo_root else None,
            },
            "editors": [
                {
                    "name": editor.name,
                    "is_available": editor.is_available(),
                    "is_current": current_editor is not None and editor.name == current_editor.name,
                }
                for editor in editors.get_all_editors()
            ],
            "agents": [
                {
                    "name": agent.name,
                    "is_available": agent.is_available(),
                    "is_current": current_agent is not None and agent.name == current_agent.name,
                }
                for agent in coding_agents.get_all_agents()
            ],
            "terminals": [
                {
                    "name": terminal.name,
                    "is_available": terminal.is_available(),
                    "is_current": current_terminal is not None
                    and terminal.name == current_terminal.name,
                }
                for terminal in terminals.get_all_terminals()
            ],
        }
        print(json.dumps(data))
        return

    console.print("[bold]Dev Doctor[/bold]\n")

    _doctor_check_git()
    console.print()

    # Check editors
    console.print("[bold]Editors:[/bold]")
    for editor in editors.get_all_editors():
        is_current = current_editor is not None and editor.name == current_editor.name
        _print_item_status(editor.name, editor.is_available(), is_current)
    console.print()

    # Check agents
    console.print("[bold]AI Coding Agents:[/bold]")
    for agent in coding_agents.get_all_agents():
        is_current = current_agent is not None and agent.name == current_agent.name
        _print_item_status(agent.name, agent.is_available(), is_current)
    console.print()

    # Check terminals
    console.print("[bold]Terminals:[/bold]")
    for terminal in terminals.get_all_terminals():
        is_current = current_terminal is not None and terminal.name == current_terminal.name
        _print_item_status(terminal.name, terminal.is_available(), is_current, "not available")


def _get_skill_source_dir() -> Path:
    """Get the path to the bundled skill files."""
    return Path(__file__).parent / "skill"


def _get_current_repo_root() -> Path | None:
    """Get the current repository root (works in worktrees too)."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())
    return None


@app.command("install-skill")
def install_skill(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing skill files if already installed"),
    ] = False,
) -> None:
    """Install Claude Code skill for parallel agent orchestration.

    Installs a skill that teaches Claude Code how to use `agent-cli dev` to
    spawn parallel AI coding agents in isolated git worktrees.

    **What it does:**

    - Copies skill files to `.claude/skills/agent-cli-dev/` in current repo
    - Enables Claude Code to automatically spawn parallel agents
    - Works when you ask to "work on multiple features" or "parallelize tasks"

    **Alternative:** Install globally via Claude Code plugin marketplace:
    `claude plugin marketplace add basnijholt/agent-cli`
    """
    # Use current repo root (works in worktrees too)
    repo_root = _get_current_repo_root()
    if repo_root is None:
        _error("Not in a git repository")

    skill_source = _get_skill_source_dir()
    skill_dest = repo_root / ".claude" / "skills" / "agent-cli-dev"

    # Check if skill source exists
    if not skill_source.exists():
        _error(f"Skill source not found: {skill_source}")

    # Check if already installed
    if skill_dest.exists() and not force:
        _warn(f"Skill already installed at {skill_dest}")
        console.print("[dim]Use --force to overwrite[/dim]")
        raise typer.Exit(0)

    # Create destination directory
    skill_dest.parent.mkdir(parents=True, exist_ok=True)

    # Copy skill files
    if skill_dest.exists():
        shutil.rmtree(skill_dest)

    shutil.copytree(skill_source, skill_dest)

    _success(f"Installed skill to {skill_dest}")
    console.print()
    console.print("[bold]What's next?[/bold]")
    console.print("  • Claude Code will automatically use this skill when relevant")
    console.print("  • Ask Claude to 'work on multiple features in parallel'")
    console.print("  • Or ask 'spawn agents for auth, payments, and notifications'")
    console.print()
    console.print("[dim]Skill files:[/dim]")
    for f in sorted(skill_dest.iterdir()):
        console.print(f"  • {f.name}")
