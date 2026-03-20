"""Launch preparation helpers for `agent-cli dev`."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._config import get_dev_child_table, get_dev_config, get_dev_table
from ._output import info

if TYPE_CHECKING:
    from .coding_agents.base import CodingAgent


@dataclass(frozen=True)
class LaunchContext:
    """Context provided to built-in preparation and user hooks."""

    agent: CodingAgent
    worktree_path: Path
    repo_root: Path
    branch: str | None
    worktree_name: str
    task_file: Path | None
    agent_env: dict[str, str]


def _normalize_hook_commands(value: Any, *, config_key: str) -> list[str]:
    """Normalize a hook config entry to a list of shell commands."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = f"{config_key} must be a string or list of strings"
        raise RuntimeError(msg)
    commands = [item.strip() for item in value if item.strip()]
    if len(commands) != len(value):
        msg = f"{config_key} contains an empty command"
        raise RuntimeError(msg)
    return commands


def _load_dev_hook_settings(agent_name: str) -> tuple[bool, list[str]]:
    """Load auto-trust and pre-launch hook settings for an agent."""
    auto_trust = bool(get_dev_config().get("auto_trust", True))
    global_hooks = get_dev_table("hooks")
    agent_hooks = get_dev_child_table("hooks", agent_name)

    pre_launch_hooks = _normalize_hook_commands(
        global_hooks.get("pre_launch"),
        config_key="[dev.hooks].pre_launch",
    )
    pre_launch_hooks.extend(
        _normalize_hook_commands(
            agent_hooks.get("pre_launch"),
            config_key=f"[dev.hooks.{agent_name}].pre_launch",
        ),
    )
    return auto_trust, pre_launch_hooks


def _build_hook_env(context: LaunchContext) -> dict[str, str]:
    """Build the environment passed to pre-launch hooks."""
    env = os.environ.copy()
    env.update(context.agent_env)
    env.update(
        {
            "AGENT_CLI_AGENT": context.agent.name,
            "AGENT_CLI_WORKTREE": str(context.worktree_path),
            "AGENT_CLI_REPO_ROOT": str(context.repo_root),
            "AGENT_CLI_BRANCH": context.branch or "",
            "AGENT_CLI_NAME": context.worktree_name,
            "AGENT_CLI_TASK_FILE": str(context.task_file or ""),
            # Keep the proposal name as an alias for compatibility.
            "AGENT_CLI_PROMPT_FILE": str(context.task_file or ""),
        },
    )
    return env


def _resolve_hook_command(command: str) -> list[str]:
    """Parse a configured hook command into argv."""
    argv = shlex.split(command)
    if not argv:
        msg = "Hook command cannot be empty"
        raise RuntimeError(msg)

    first = Path(argv[0]).expanduser()
    if argv[0].startswith("~") or "/" in argv[0]:
        argv[0] = str(first)
    return argv


def _run_pre_launch_hook(command: str, context: LaunchContext) -> None:
    """Run a single pre-launch hook."""
    argv = _resolve_hook_command(command)
    info(f"Running pre-launch hook: {command}")
    try:
        result = subprocess.run(
            argv,
            cwd=context.worktree_path,
            env=_build_hook_env(context),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        msg = f"Pre-launch hook not found: {argv[0]}"
        raise RuntimeError(msg) from e

    if result.returncode == 0:
        return

    details = (result.stderr or result.stdout).strip()
    msg = f"Pre-launch hook failed ({result.returncode}): {command}"
    if details:
        msg += f"\n{details}"
    raise RuntimeError(msg)


def prepare_agent_launch(context: LaunchContext, *, hooks_enabled: bool = True) -> None:
    """Run built-in preparation and configured pre-launch hooks."""
    if not hooks_enabled:
        return

    auto_trust, pre_launch_hooks = _load_dev_hook_settings(context.agent.name)
    if auto_trust and (
        message := context.agent.prepare_launch(context.worktree_path, context.repo_root)
    ):
        info(message)

    for command in pre_launch_hooks:
        _run_pre_launch_hook(command, context)
