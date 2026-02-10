"""Polling logic for agent orchestration."""

from __future__ import annotations

import time
from pathlib import Path

from . import agent_state, tmux_ops

# Seconds of unchanged output before marking an agent as "quiet".
QUIET_SECONDS = 10.0


def _check_agent_status(agent: agent_state.TrackedAgent) -> None:
    """Check and update a single agent's status in-place."""
    if not tmux_ops.pane_exists(agent.pane_id):
        agent.status = "dead"
        return

    if agent.agent_type == "claude":
        done_path = Path(agent.worktree_path) / ".claude" / "DONE"
        if done_path.exists():
            agent.status = "done"
            return

    agent.status = "running"


def _check_quiescence(agent: agent_state.TrackedAgent, now: float) -> None:
    """Track output changes and mark agent as quiet if output is stable."""
    output = tmux_ops.capture_pane(agent.pane_id)
    if output is None:
        return

    output_hash = tmux_ops.hash_output(output)
    if output_hash != agent.last_output_hash:
        agent.last_output_hash = output_hash
        agent.last_output_change_at = now
        return

    # Hash unchanged — mark quiet if enough wall-clock time has passed
    if agent.last_output_change_at > 0 and (now - agent.last_output_change_at) >= QUIET_SECONDS:
        agent.status = "quiet"


def poll_once(repo_root: Path) -> dict[str, str]:
    """Perform a single poll of all tracked agents.

    Checks pane existence, completion sentinels, and output quiescence.
    Updates the state file and returns ``{agent_name: status}``.
    """
    state = agent_state.load_state(repo_root)
    now = time.time()

    for agent in state.agents.values():
        _check_agent_status(agent)
        if agent.status == "running":
            _check_quiescence(agent, now)

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

    Returns ``(final_status, elapsed_seconds)`` where ``final_status`` is one
    of ``done``, ``dead``, or ``quiet``.
    Raises ``TimeoutError`` if *timeout* > 0 and is exceeded.
    Raises ``KeyError`` if the agent is not found.
    """
    state = agent_state.load_state(repo_root)
    if name not in state.agents:
        msg = f"Agent '{name}' not found"
        raise KeyError(msg)

    start = time.time()

    while True:
        elapsed = time.time() - start
        if timeout > 0 and elapsed >= timeout:
            msg = f"Timeout after {elapsed:.0f}s"
            raise TimeoutError(msg)

        statuses = poll_once(repo_root)
        status = statuses.get(name, "dead")

        if status in ("dead", "done", "quiet"):
            return status, elapsed

        time.sleep(interval)
