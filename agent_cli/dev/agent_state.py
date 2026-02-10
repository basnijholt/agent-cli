"""Agent state tracking for orchestration."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Literal

STATE_BASE = Path.home() / ".cache" / "agent-cli"

AgentStatus = Literal["running", "done", "dead"]


@dataclass
class TrackedAgent:
    """A single tracked agent instance."""

    name: str
    pane_id: str
    worktree_path: str
    agent_type: str
    started_at: float
    status: AgentStatus = "running"


@dataclass
class AgentStateFile:
    """State file for one repository's tracked agents."""

    agents: dict[str, TrackedAgent] = field(default_factory=dict)
    last_poll_at: float = 0.0


def _repo_slug(repo_root: Path) -> str:
    """Convert a repo root path to a filesystem-safe slug.

    Includes a short path hash to avoid collisions between repositories with
    the same trailing directory names.
    """
    parts = repo_root.parts[-2:]
    slug = "_".join(parts)
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", slug)
    digest = sha256(str(repo_root.expanduser().resolve()).encode()).hexdigest()[:10]
    return f"{slug}_{digest}"


def _state_dir(repo_root: Path) -> Path:
    """Return the state directory for a repo."""
    return STATE_BASE / _repo_slug(repo_root)


def _state_file_path(repo_root: Path) -> Path:
    """Return the path to the agents.json state file."""
    return _state_dir(repo_root) / "agents.json"


def load_state(repo_root: Path) -> AgentStateFile:
    """Load agent state from disk.

    Returns an empty state if the file does not exist or is corrupt.
    """
    path = _state_file_path(repo_root)
    if not path.exists():
        return AgentStateFile()

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, TypeError):
        return AgentStateFile()

    agents: dict[str, TrackedAgent] = {}
    for name, agent_data in data.get("agents", {}).items():
        status = agent_data.get("status", "running")
        if status not in ("running", "done", "dead"):
            status = "running"
        try:
            agents[name] = TrackedAgent(
                name=str(agent_data["name"]),
                pane_id=str(agent_data["pane_id"]),
                worktree_path=str(agent_data["worktree_path"]),
                agent_type=str(agent_data["agent_type"]),
                started_at=float(agent_data["started_at"]),
                status=status,
            )
        except (KeyError, TypeError, ValueError):
            continue

    raw_last_poll_at = data.get("last_poll_at", 0.0)
    try:
        last_poll_at = float(raw_last_poll_at)
    except (TypeError, ValueError):
        last_poll_at = 0.0
    return AgentStateFile(agents=agents, last_poll_at=last_poll_at)


def save_state(repo_root: Path, state: AgentStateFile) -> None:
    """Atomically write state to disk."""
    path = _state_file_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "agents": {name: asdict(agent) for name, agent in state.agents.items()},
        "last_poll_at": state.last_poll_at,
    }
    # Write to temp file then rename for atomicity
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.rename(path)


def register_agent(
    repo_root: Path,
    name: str,
    pane_id: str,
    worktree_path: Path,
    agent_type: str,
) -> TrackedAgent:
    """Register a new tracked agent in the state file."""
    state = load_state(repo_root)
    # Keep only active agents; terminal entries should not reserve names forever.
    for existing_name in list(state.agents):
        if state.agents[existing_name].status in ("done", "dead"):
            del state.agents[existing_name]

    now = time.time()
    agent = TrackedAgent(
        name=name,
        pane_id=pane_id,
        worktree_path=str(worktree_path),
        agent_type=agent_type,
        started_at=now,
    )
    state.agents[name] = agent
    save_state(repo_root, state)
    return agent


def generate_agent_name(
    repo_root: Path,
    worktree_path: Path,
    agent_type: str,
    explicit_name: str | None = None,
) -> str:
    """Generate a unique agent name.

    If *explicit_name* is given, uses that (raises if it collides with an active
    agent).
    Otherwise auto-generates from the worktree branch name.
    """
    state = load_state(repo_root)
    existing = {
        name for name, existing_agent in state.agents.items() if existing_agent.status == "running"
    }

    if explicit_name:
        if explicit_name in existing:
            msg = f"Agent name '{explicit_name}' already exists. Use a different --name."
            raise ValueError(msg)
        return explicit_name

    # Use worktree directory name as base (which is the branch name)
    base = worktree_path.name

    # First agent in this worktree: just use the branch name
    if base not in existing:
        return base

    # Subsequent agents: append agent type
    candidate = f"{base}-{agent_type}"
    if candidate not in existing:
        return candidate

    # Still collides: add numeric suffix
    n = 2
    while f"{candidate}-{n}" in existing:
        n += 1
    return f"{candidate}-{n}"


def inject_completion_hook(worktree_path: Path, agent_type: str) -> None:
    """Inject a Stop hook into .claude/settings.local.json for completion detection.

    Uses settings.local.json (not settings.json) to avoid dirtying tracked files.
    Only applies to Claude Code agents. Merges with existing settings.
    """
    if agent_type != "claude":
        return

    settings_path = worktree_path / ".claude" / "settings.local.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings: dict = {}
    if settings_path.exists():
        try:
            raw = json.loads(settings_path.read_text())
            settings = raw if isinstance(raw, dict) else {}
        except json.JSONDecodeError:
            settings = {}

    # Merge Stop hook
    hooks = settings.setdefault("hooks", {})
    stop_hooks = hooks.setdefault("Stop", [])

    # Check if our hook is already present
    sentinel_cmd = "touch .claude/DONE"
    for entry in stop_hooks:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "") if isinstance(hook, dict) else hook
            if sentinel_cmd in cmd:
                return  # Already injected

    stop_hooks.append(
        {
            "matcher": "",
            "hooks": [{"type": "command", "command": sentinel_cmd}],
        },
    )
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")


def is_tmux() -> bool:
    """Check if tmux is available (inside a session or server is reachable)."""
    if os.environ.get("TMUX"):
        return True
    # Not inside tmux, but check if a tmux server is running
    import subprocess  # noqa: PLC0415

    try:
        subprocess.run(
            ["tmux", "list-sessions"],  # noqa: S607
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
