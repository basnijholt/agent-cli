"""Terminal adapters for the dev module."""

from __future__ import annotations

from .base import Terminal
from .registry import (
    detect_current_terminal,
    get_all_terminals,
    get_available_terminals,
    get_terminal,
)

__all__ = [
    "Terminal",
    "detect_current_terminal",
    "get_all_terminals",
    "get_available_terminals",
    "get_terminal",
]
