"""AI coding agent adapters for the dev module."""

from __future__ import annotations

from .base import CodingAgent
from .registry import (
    detect_current_agent,
    get_agent,
    get_all_agents,
    get_available_agents,
)

__all__ = [
    "CodingAgent",
    "detect_current_agent",
    "get_agent",
    "get_all_agents",
    "get_available_agents",
]
