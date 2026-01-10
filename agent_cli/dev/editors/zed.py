"""Zed editor adapter."""

from __future__ import annotations

import os

from .base import Editor, _get_term_program


class Zed(Editor):
    """Zed - A high-performance, multiplayer code editor."""

    name = "zed"
    command = "zed"
    alt_commands = ()
    install_url = "https://zed.dev"

    def detect(self) -> bool:
        """Detect if running inside Zed's integrated terminal."""
        term_program = _get_term_program()
        if term_program is not None and "zed" in term_program.lower():
            return True
        # Zed also sets ZED_TERM
        return os.environ.get("ZED_TERM") is not None
