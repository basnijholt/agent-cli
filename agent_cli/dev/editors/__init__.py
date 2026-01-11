"""Editor adapters for the dev module."""

from __future__ import annotations

from .base import Editor
from .registry import (
    detect_current_editor,
    get_all_editors,
    get_available_editors,
    get_editor,
)

__all__ = [
    "Editor",
    "detect_current_editor",
    "get_all_editors",
    "get_available_editors",
    "get_editor",
]
