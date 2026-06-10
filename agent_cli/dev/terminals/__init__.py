"""Terminal adapters for the dev module."""

from __future__ import annotations

from .base import Multiplexer, Terminal, TerminalHandle
from .registry import (
    detect_current_terminal,
    get_all_terminals,
    get_available_terminals,
    get_terminal,
)

__all__ = [
    "Multiplexer",
    "Terminal",
    "TerminalHandle",
    "detect_current_terminal",
    "get_all_terminals",
    "get_available_terminals",
    "get_terminal",
]
