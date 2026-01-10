"""Registry for AI coding agent adapters."""

from __future__ import annotations

from .aider import Aider
from .base import CodingAgent  # noqa: TC001
from .claude import ClaudeCode
from .codex import Codex
from .gemini import Gemini

# All available coding agents
_AGENTS: list[type[CodingAgent]] = [
    ClaudeCode,
    Codex,
    Gemini,
    Aider,
]

# Cache for agent instances
_agent_instances: dict[str, CodingAgent] = {}


def get_all_agents() -> list[CodingAgent]:
    """Get instances of all registered coding agents."""
    agents = []
    for agent_cls in _AGENTS:
        name = agent_cls.name
        if name not in _agent_instances:
            _agent_instances[name] = agent_cls()
        agents.append(_agent_instances[name])
    return agents


def get_available_agents() -> list[CodingAgent]:
    """Get all installed/available coding agents."""
    return [agent for agent in get_all_agents() if agent.is_available()]


def detect_current_agent() -> CodingAgent | None:
    """Detect which coding agent we're currently running in."""
    for agent in get_all_agents():
        if agent.detect():
            return agent
    return None


def get_agent(name: str) -> CodingAgent | None:
    """Get a coding agent by name."""
    name_lower = name.lower()
    for agent in get_all_agents():
        if agent.name.lower() == name_lower:
            return agent
        if agent.command.lower() == name_lower:
            return agent
    return None
