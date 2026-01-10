"""Cursor editor adapter."""

from __future__ import annotations

import os

from .base import Editor, _get_term_program


class Cursor(Editor):
    """Cursor - AI-first code editor."""

    name = "cursor"
    command = "cursor"
    alt_commands = ()
    install_url = "https://cursor.com"

    def detect(self) -> bool:
        """Detect if running inside Cursor's integrated terminal."""
        # Check TERM_PROGRAM (Cursor is VS Code-based, may set this)
        term_program = _get_term_program()
        if term_program is not None and "cursor" in term_program.lower():
            return True
        # Cursor Agent sets CURSOR_AGENT env var
        return os.environ.get("CURSOR_AGENT") is not None
