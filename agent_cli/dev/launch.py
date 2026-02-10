"""Agent and editor resolution, configuration, and launching."""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from agent_cli.config import load_config
from agent_cli.core.utils import console

from . import coding_agents, editors, terminals, worktree

if TYPE_CHECKING:
    from .coding_agents.base import CodingAgent
    from .editors.base import Editor


def resolve_editor(
    use_editor: bool,
    editor_name: str | None,
    default_editor: str | None = None,
) -> Editor | None:
    """Resolve which editor to use based on flags and config defaults."""
    # Use explicit name if provided
    if editor_name:
        editor = editors.get_editor(editor_name)
        if editor is None:
            from ._output import _warn  # noqa: PLC0415

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
        from ._output import _warn  # noqa: PLC0415

        _warn(f"Default editor '{default_editor}' from config not found")

    # Auto-detect current or first available
    editor = editors.detect_current_editor()
    if editor is None:
        available = editors.get_available_editors()
        return available[0] if available else None
    return editor


def resolve_agent(
    use_agent: bool,
    agent_name: str | None,
    default_agent: str | None = None,
) -> CodingAgent | None:
    """Resolve which coding agent to use based on flags and config defaults."""
    # Use explicit name if provided
    if agent_name:
        agent = coding_agents.get_agent(agent_name)
        if agent is None:
            from ._output import _warn  # noqa: PLC0415

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
        from ._output import _warn  # noqa: PLC0415

        _warn(f"Default agent '{default_agent}' from config not found")

    # Auto-detect current or first available
    agent = coding_agents.detect_current_agent()
    if agent is None:
        available = coding_agents.get_available_agents()
        return available[0] if available else None
    return agent


def get_config_agent_args() -> dict[str, list[str]] | None:
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


def get_config_agent_env() -> dict[str, dict[str, str]] | None:
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

    return result or None


def get_agent_env(agent: CodingAgent) -> dict[str, str]:
    """Get environment variables for an agent.

    Merges config env vars with agent's built-in env vars.
    Config env vars take precedence.
    """
    # Start with agent's built-in env vars
    env = agent.get_env().copy()

    # Add config env vars (these override built-in ones)
    config_env = get_config_agent_env()
    if config_env and agent.name in config_env:
        env.update(config_env[agent.name])

    return env


def merge_agent_args(
    agent: CodingAgent,
    cli_args: list[str] | None,
) -> list[str] | None:
    """Merge CLI args with config args for an agent.

    Config args are applied first, CLI args are appended (and can override).
    """
    config_args = get_config_agent_args()
    result: list[str] = []

    # Add config args for this agent
    if config_args and agent.name in config_args:
        result.extend(config_args[agent.name])

    # Add CLI args (these override/extend config args)
    if cli_args:
        result.extend(cli_args)

    return result or None


def _is_ssh_session() -> bool:
    """Check if we're in an SSH session."""
    return bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"))


def launch_editor(path: Path, editor: Editor) -> None:
    """Launch editor via subprocess (editors are GUI apps that detach)."""
    from ._output import _success, _warn  # noqa: PLC0415

    try:
        subprocess.Popen(editor.open_command(path))
        _success(f"Opened {editor.name}")
    except Exception as e:
        _warn(f"Could not open editor: {e}")


def write_prompt_to_worktree(worktree_path: Path, prompt: str) -> Path:
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


def _create_prompt_wrapper_script(
    worktree_path: Path,
    agent: CodingAgent,
    task_file: Path,
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    """Create a wrapper script that reads prompt from file to avoid shell quoting issues."""
    script_path = Path(tempfile.gettempdir()) / f"agent-cli-{worktree_path.name}.sh"

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

    task_file_rel = task_file.relative_to(worktree_path)
    script_content = f"""#!/usr/bin/env bash
# Auto-generated script to launch agent with prompt
# Reads prompt from file to avoid shell parsing issues with special characters
{env_prefix}exec {agent_cmd} "$(cat {shlex.quote(str(task_file_rel))})"
"""
    script_path.write_text(script_content)
    script_path.chmod(0o755)
    return script_path


def launch_agent(
    path: Path,
    agent: CodingAgent,
    extra_args: list[str] | None = None,
    prompt: str | None = None,
    task_file: Path | None = None,
    env: dict[str, str] | None = None,
    *,
    track: bool = True,
    agent_name: str | None = None,
) -> str | None:
    """Launch agent in a new terminal tab.

    Agents are interactive TUIs that need a proper terminal.
    Priority: tmux/zellij tab > terminal tab > print instructions.

    When *track* is ``True`` and tmux is detected, the agent is registered
    in the orchestration state file so it can be monitored with ``dev poll``,
    ``dev output``, ``dev send``, and ``dev wait``.

    Returns the tracked agent name if tracking was successful, else ``None``.
    """
    from ._output import _success, _warn  # noqa: PLC0415
    from .terminals.tmux import Tmux  # noqa: PLC0415

    terminal = terminals.detect_current_terminal()

    # Use wrapper script when opening in a terminal tab - all terminals pass commands
    # through a shell, so special characters get interpreted. Reading from file avoids this.
    if task_file and terminal is not None:
        script_path = _create_prompt_wrapper_script(path, agent, task_file, extra_args, env)
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

        # Use tmux_ops for tracked launch when in tmux
        if isinstance(terminal, Tmux) and track:
            from . import agent_state, tmux_ops  # noqa: PLC0415

            pane_id = tmux_ops.open_window_with_pane_id(path, full_cmd, tab_name=tab_name)
            if pane_id:
                root = repo_root or path
                name = agent_state.generate_agent_name(root, path, agent.name, agent_name)
                agent_state.register_agent(root, name, pane_id, path, agent.name)
                agent_state.inject_completion_hook(path, agent.name)
                _success(f"Started {agent.name} in new tmux tab (tracking as [cyan]{name}[/cyan])")
                return name
            _warn("Could not open new tmux window")
        elif terminal.open_new_tab(path, full_cmd, tab_name=tab_name):
            _success(f"Started {agent.name} in new {terminal.name} tab")
            return None
        else:
            _warn(f"Could not open new tab in {terminal.name}")

    # No terminal detected or failed - print instructions
    if _is_ssh_session():
        console.print("\n[yellow]SSH session without terminal multiplexer.[/yellow]")
        console.print("[bold]Start a multiplexer first, then run:[/bold]")
    else:
        console.print(f"\n[bold]To start {agent.name}:[/bold]")
    console.print(f"  cd {path}")
    console.print(f"  {full_cmd}")
    return None
