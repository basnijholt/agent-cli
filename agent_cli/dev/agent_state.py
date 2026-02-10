"""Agent state tracking for orchestration."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

STATE_BASE = Path.home() / ".cache" / "agent-cli"

AgentStatus = Literal["running", "idle", "done", "dead"]


@dataclass
class TrackedAgent:
    """A single tracked agent instance."""

    name: str
    pane_id: str
    worktree_path: str
    agent_type: str
    started_at: float
    status: AgentStatus = "running"
    last_output_hash: str = ""
    last_change_at: float = 0.0


@dataclass
class AgentStateFile:
    """State file for one repository's tracked agents."""

    repo_root: str
    agents: dict[str, TrackedAgent] = field(default_factory=dict)
    last_poll_at: float = 0.0


def _repo_slug(repo_root: Path) -> str:
    """Convert a repo root path to a filesystem-safe slug."""
    # Use the last two path components for readability, e.g. "Work_my-project"
    parts = repo_root.parts[-2:]
    slug = "_".join(parts)
    # Sanitize: keep only alphanumeric, dash, underscore
    return re.sub(r"[^a-zA-Z0-9_-]", "_", slug)


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
        return AgentStateFile(repo_root=str(repo_root))

    try:
        data = json.loads(path.read_text())
        agents = {}
        for name, agent_data in data.get("agents", {}).items():
            agents[name] = TrackedAgent(**agent_data)
        return AgentStateFile(
            repo_root=data.get("repo_root", str(repo_root)),
            agents=agents,
            last_poll_at=data.get("last_poll_at", 0.0),
        )
    except (json.JSONDecodeError, TypeError, KeyError):
        return AgentStateFile(repo_root=str(repo_root))


def save_state(repo_root: Path, state: AgentStateFile) -> None:
    """Atomically write state to disk."""
    path = _state_file_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "repo_root": state.repo_root,
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
    now = time.time()
    agent = TrackedAgent(
        name=name,
        pane_id=pane_id,
        worktree_path=str(worktree_path),
        agent_type=agent_type,
        started_at=now,
        last_change_at=now,
    )
    state.agents[name] = agent
    save_state(repo_root, state)
    return agent


def unregister_agent(repo_root: Path, name: str) -> bool:
    """Remove an agent from the state file.

    Returns ``True`` if the agent was found and removed.
    """
    state = load_state(repo_root)
    if name not in state.agents:
        return False
    del state.agents[name]
    save_state(repo_root, state)
    return True


def generate_agent_name(
    repo_root: Path,
    worktree_path: Path,
    agent_type: str,
    explicit_name: str | None = None,
) -> str:
    """Generate a unique agent name.

    If *explicit_name* is given, uses that (raises if it collides).
    Otherwise auto-generates from the worktree branch name.
    """
    state = load_state(repo_root)
    existing = set(state.agents.keys())

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
