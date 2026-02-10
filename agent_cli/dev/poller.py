"""Background poller daemon for agent orchestration."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import agent_state, tmux_ops


def poll_once(repo_root: Path) -> dict[str, str]:
    """Perform a single poll of all tracked agents.

    Checks pane existence, completion sentinels, and output quiescence.
    Updates the state file and returns ``{agent_name: status}``.
    """
    state = agent_state.load_state(repo_root)
    now = time.time()
    result: dict[str, str] = {}

    for agent in state.agents.values():
        if not tmux_ops.pane_exists(agent.pane_id):
            agent.status = "dead"
            result[agent.name] = "dead"
            continue

        done_path = Path(agent.worktree_path) / ".claude" / "DONE"
        if done_path.exists():
            agent.status = "done"
            result[agent.name] = "done"
            continue

        output = tmux_ops.capture_pane(agent.pane_id)
        if output is not None:
            h = tmux_ops.hash_output(output)
            if h != agent.last_output_hash:
                agent.last_output_hash = h
                agent.last_change_at = now
                agent.status = "running"
            else:
                agent.status = "idle"
        result[agent.name] = agent.status

    state.last_poll_at = now
    agent_state.save_state(repo_root, state)
    return result


def _pid_file_path(repo_root: Path) -> Path:
    """Return the PID file path for the poller daemon."""
    return agent_state._state_dir(repo_root) / "poller.pid"


def is_poller_running(repo_root: Path) -> bool:
    """Check if the poller daemon is running."""
    pid_file = _pid_file_path(repo_root)
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        pid_file.unlink(missing_ok=True)
        return False


def run_poller_daemon(repo_root: Path, interval: float = 5.0) -> None:
    """Run the poller loop (called inside the daemon process).

    Handles SIGTERM/SIGINT for graceful shutdown.
    Auto-stops when all agents are done or dead.
    """
    running = True

    def _handle_signal(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    pid_file = _pid_file_path(repo_root)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))

    try:
        while running:
            statuses = poll_once(repo_root)
            # Auto-stop if no agents are running or idle
            if statuses and all(s in ("done", "dead") for s in statuses.values()):
                break
            time.sleep(interval)
    finally:
        pid_file.unlink(missing_ok=True)


def start_poller(repo_root: Path, interval: float = 5.0) -> int | None:
    """Start the background poller as a detached subprocess.

    Returns the PID of the poller process, or ``None`` on failure.
    """
    if is_poller_running(repo_root):
        return None

    cmd = [
        sys.executable,
        "-m",
        "agent_cli.dev.poller",
        str(repo_root),
        str(interval),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return proc.pid


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

        if not tmux_ops.pane_exists(agent.pane_id):
            _update_agent_status(repo_root, name, "dead")
            return "dead", elapsed

        done_path = Path(agent.worktree_path) / ".claude" / "DONE"
        if done_path.exists():
            _update_agent_status(repo_root, name, "done")
            return "done", elapsed

        output = tmux_ops.capture_pane(agent.pane_id)
        if output is not None:
            h = tmux_ops.hash_output(output)
            if h == agent.last_output_hash:
                consecutive_idle += 1
            else:
                consecutive_idle = 0
                agent.last_output_hash = h
                agent.last_change_at = time.time()

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


def stop_poller(repo_root: Path) -> bool:
    """Stop the background poller by sending SIGTERM."""
    pid_file = _pid_file_path(repo_root)
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        pid_file.unlink(missing_ok=True)
        return False


if __name__ == "__main__":
    # Entry point for the daemon subprocess
    if len(sys.argv) >= 2:  # noqa: PLR2004
        _repo_root = Path(sys.argv[1])
        _interval = float(sys.argv[2]) if len(sys.argv) >= 3 else 5.0  # noqa: PLR2004
        run_poller_daemon(_repo_root, _interval)
