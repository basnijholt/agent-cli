"""Cursor editor adapter."""

from __future__ import annotations

from .base import Editor, _get_term_program


class Cursor(Editor):
    """Cursor - AI-first code editor."""

    name = "cursor"
    command = "cursor"
    alt_commands = ()
    install_url = "https://cursor.com"

    def detect(self) -> bool:
        """Detect if running inside Cursor's integrated terminal."""
        term_program = _get_term_program()
        return term_program is not None and "cursor" in term_program.lower()
