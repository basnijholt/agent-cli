"""Registry for AI coding agent adapters."""

from __future__ import annotations

from agent_cli.dev.registry import Registry

from .aider import Aider
from .base import CodingAgent  # noqa: TC001
from .claude import ClaudeCode
from .codex import Codex
from .continue_dev import ContinueDev
from .copilot import Copilot
from .cursor_agent import CursorAgent
from .gemini import Gemini
from .opencode import OpenCode

# All available coding agents (in priority order for detection)
_AGENTS: list[type[CodingAgent]] = [
    ClaudeCode,
    Codex,
    Gemini,
    Aider,
    Copilot,
    ContinueDev,
    OpenCode,
    CursorAgent,
]

_registry: Registry[CodingAgent] = Registry(_AGENTS)


def get_all_agents() -> list[CodingAgent]:
    """Get instances of all registered coding agents."""
    return _registry.get_all()


def get_available_agents() -> list[CodingAgent]:
    """Get all installed/available coding agents."""
    return _registry.get_available()


def detect_current_agent() -> CodingAgent | None:
    """Detect which coding agent we're currently running in."""
    return _registry.detect_current()


def get_agent(name: str) -> CodingAgent | None:
    """Get a coding agent by name."""
    return _registry.get_by_name(name)
