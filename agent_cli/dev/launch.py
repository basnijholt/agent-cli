"""Agent and editor resolution, configuration, and launching."""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from agent_cli.core.utils import console

from . import coding_agents, editors, terminals, worktree
from ._config import get_dev_child_tables, get_dev_table
from ._output import success, warn

if TYPE_CHECKING:
    from .coding_agents.base import CodingAgent
    from .editors.base import Editor
    from .terminals import TerminalHandle


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
            warn(f"Editor '{editor_name}' not found")
        return editor

    # If no flag and no default, don't use an editor
    if not use_editor and not default_editor:
        return None

    # If default is set in config, use it
    if default_editor:
        editor = editors.get_editor(default_editor)
        if editor is not None:
            return editor
        warn(f"Default editor '{default_editor}' from config not found")

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
            warn(f"Agent '{agent_name}' not found")
        return agent

    # If no flag and no default, don't use an agent
    if not use_agent and not default_agent:
        return None

    # If default is set in config, use it
    if default_agent:
        agent = coding_agents.get_agent(default_agent)
        if agent is not None:
            return agent
        warn(f"Default agent '{default_agent}' from config not found")

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
    agent_args = get_dev_table("agent_args")
    return agent_args or None


def get_config_agent_env() -> dict[str, dict[str, str]] | None:
    """Load agent_env from config file.

    Config format:
        [dev.agent_env]
        claude = { CLAUDE_CODE_USE_VERTEX = "1", ANTHROPIC_MODEL = "opus" }

    Note: The config loader flattens nested dicts, so keys like
    'dev.agent_env.claude' become top-level. We reconstruct the
    agent_env dict from these flattened keys.
    """
    agent_env = get_dev_child_tables("agent_env")
    return agent_env or None


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
    try:
        subprocess.Popen(editor.open_command(path))
        success(f"Opened {editor.name}")
    except Exception as e:
        warn(f"Could not open editor: {e}")


def write_prompt_to_worktree(worktree_path: Path, prompt: str) -> Path:
    """Write the prompt to a unique file in .claude/ in the worktree.

    Uses a timestamp and random suffix to avoid overwrites when multiple
    agents are launched in parallel on the same worktree.
    """
    import time  # noqa: PLC0415

    claude_dir = worktree_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    suffix = os.urandom(2).hex()
    task_file = claude_dir / f"TASK-{timestamp}-{suffix}.md"
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
    fd, script_path_str = tempfile.mkstemp(
        prefix=f"agent-cli-{worktree_path.name}-",
        suffix=".sh",
    )
    os.write(fd, script_content.encode())
    os.close(fd)
    script_path = Path(script_path_str)
    script_path.chmod(0o755)
    return script_path


def _resolve_launch_terminal(multiplexer_name: str | None) -> terminals.Terminal | None:
    """Resolve the terminal or multiplexer to use for launching."""
    terminal = terminals.get_terminal(multiplexer_name) if multiplexer_name else None
    if terminal is not None and not terminal.is_available():
        warn(f"{terminal.name} is not installed")
        return None
    return terminal or terminals.detect_current_terminal()


def _build_agent_launch_command(
    path: Path,
    agent: CodingAgent,
    extra_args: list[str] | None,
    prompt: str | None,
    task_file: Path | None,
    env: dict[str, str] | None,
    terminal: terminals.Terminal | None,
) -> str:
    """Build the command string used to launch an agent in a terminal."""
    if task_file and terminal is not None:
        script_path = _create_prompt_wrapper_script(path, agent, task_file, extra_args, env)
        return f"bash {shlex.quote(str(script_path))}"

    agent_cmd = shlex.join(agent.launch_command(path, extra_args, prompt))
    env_prefix = _format_env_prefix(env or {})
    return env_prefix + agent_cmd


def _tab_name_for_path(path: Path) -> tuple[Path | None, str]:
    """Build the terminal tab name for a worktree path."""
    repo_root = worktree.get_main_repo_root(path)
    branch = worktree.get_current_branch(path)
    repo_name = repo_root.name if repo_root else path.name
    tab_name = f"{repo_name}@{branch}" if branch else repo_name
    return repo_root, tab_name


def _launch_in_tmux(
    path: Path,
    agent: CodingAgent,
    terminal: terminals.Terminal,
    full_cmd: str,
    tab_name: str,
    repo_root: Path | None,
    multiplexer_name: str | None,
) -> TerminalHandle | None:
    """Launch an agent via tmux and return its pane handle."""
    from .terminals.tmux import Tmux  # noqa: PLC0415

    if not isinstance(terminal, Tmux):
        warn("Could not open new tab in tmux")
        return None

    requested_tmux = multiplexer_name == "tmux"
    session_name = None
    if requested_tmux and not terminal.detect():
        session_name = terminal.session_name_for_repo(repo_root or path)

    handle = terminal.open_in_session(
        path,
        full_cmd,
        tab_name=tab_name,
        session_name=session_name,
    )
    if handle is None:
        warn("Could not open new tab in tmux")
        return None

    session_label = (
        f" in tmux session {handle.session_name}"
        if requested_tmux and handle.session_name
        else " in new tmux tab"
    )
    success(f"Started {agent.name}{session_label}")
    return handle


def _launch_in_terminal(
    path: Path,
    agent: CodingAgent,
    terminal: terminals.Terminal,
    full_cmd: str,
    tab_name: str,
    repo_root: Path | None,
    multiplexer_name: str | None,
) -> tuple[bool, TerminalHandle | None]:
    """Launch an agent in the resolved terminal."""
    if terminal.name == "tmux":
        handle = _launch_in_tmux(
            path,
            agent,
            terminal,
            full_cmd,
            tab_name,
            repo_root,
            multiplexer_name,
        )
        return handle is not None, handle

    if terminal.open_new_tab(path, full_cmd, tab_name=tab_name):
        success(f"Started {agent.name} in new {terminal.name} tab")
        return True, None

    warn(f"Could not open new tab in {terminal.name}")
    return False, None


def launch_agent(
    path: Path,
    agent: CodingAgent,
    extra_args: list[str] | None = None,
    prompt: str | None = None,
    task_file: Path | None = None,
    env: dict[str, str] | None = None,
    multiplexer_name: str | None = None,
) -> TerminalHandle | None:
    """Launch agent in a new terminal tab.

    Agents are interactive TUIs that need a proper terminal.
    Priority: tmux/zellij tab > terminal tab > print instructions.
    """
    terminal = _resolve_launch_terminal(multiplexer_name)
    full_cmd = _build_agent_launch_command(
        path, agent, extra_args, prompt, task_file, env, terminal
    )

    if terminal is not None:
        repo_root, tab_name = _tab_name_for_path(path)
        launched, handle = _launch_in_terminal(
            path,
            agent,
            terminal,
            full_cmd,
            tab_name,
            repo_root,
            multiplexer_name,
        )
        if launched:
            return handle

    # No terminal detected or failed - print instructions
    if _is_ssh_session():
        console.print("\n[yellow]SSH session without terminal multiplexer.[/yellow]")
        console.print("[bold]Start a multiplexer first, then run:[/bold]")
    else:
        console.print(f"\n[bold]To start {agent.name}:[/bold]")
    console.print(f"  cd {path}")
    console.print(f"  {full_cmd}")
    return None
