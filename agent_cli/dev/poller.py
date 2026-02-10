"""Polling logic for agent orchestration."""

from __future__ import annotations

import time
from pathlib import Path

from . import agent_state, tmux_ops


def _check_agent_status(agent: agent_state.TrackedAgent, now: float) -> None:
    """Check and update a single agent's status in-place."""
    if not tmux_ops.pane_exists(agent.pane_id):
        agent.status = "dead"
        return

    if agent.agent_type == "claude":
        done_path = Path(agent.worktree_path) / ".claude" / "DONE"
        if done_path.exists():
            agent.status = "done"
            return

    output = tmux_ops.capture_pane(agent.pane_id)
    if output is not None:
        h = tmux_ops.hash_output(output)
        if h != agent.last_output_hash:
            agent.last_output_hash = h
            agent.last_change_at = now
            agent.status = "running"
        else:
            agent.status = "idle"


def poll_once(repo_root: Path) -> dict[str, str]:
    """Perform a single poll of all tracked agents.

    Checks pane existence, completion sentinels, and output quiescence.
    Updates the state file and returns ``{agent_name: status}``.
    """
    state = agent_state.load_state(repo_root)
    now = time.time()

    for agent in state.agents.values():
        _check_agent_status(agent, now)

    state.last_poll_at = now
    agent_state.save_state(repo_root, state)
    return {a.name: a.status for a in state.agents.values()}


def wait_for_agent(
    repo_root: Path,
    name: str,
    timeout: float = 0,
    interval: float = 5.0,
) -> tuple[str, float]:
    """Block until a tracked agent finishes.

    Returns ``(final_status, elapsed_seconds)``.
    Raises ``TimeoutError`` if *timeout* > 0 and is exceeded.
    Raises ``KeyError`` if the agent is not found.
    """
    state = agent_state.load_state(repo_root)
    agent = state.agents.get(name)
    if agent is None:
        msg = f"Agent '{name}' not found"
        raise KeyError(msg)

    start = time.time()
    consecutive_idle = 0

    while True:
        elapsed = time.time() - start
        if timeout > 0 and elapsed >= timeout:
            msg = f"Timeout after {elapsed:.0f}s"
            raise TimeoutError(msg)

        _check_agent_status(agent, time.time())

        if agent.status in ("dead", "done"):
            _update_agent_status(repo_root, name, agent.status)
            return agent.status, elapsed

        if agent.status == "idle":
            consecutive_idle += 1
        else:
            consecutive_idle = 0

        # Require 2 consecutive idle polls to confirm
        if consecutive_idle >= 2:  # noqa: PLR2004
            _update_agent_status(repo_root, name, "idle")
            return "idle", elapsed

        time.sleep(interval)


def _update_agent_status(repo_root: Path, name: str, status: agent_state.AgentStatus) -> None:
    """Update a single agent's status in the state file."""
    state = agent_state.load_state(repo_root)
    if name in state.agents:
        state.agents[name].status = status
        agent_state.save_state(repo_root, state)
