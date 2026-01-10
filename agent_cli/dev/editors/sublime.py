"""Sublime Text editor adapter."""

from __future__ import annotations

from .base import Editor, _get_term_program


class SublimeText(Editor):
    """Sublime Text - A sophisticated text editor for code."""

    name = "sublime"
    command = "subl"
    alt_commands = ("sublime_text", "sublime")
    install_url = "https://www.sublimetext.com"

    def detect(self) -> bool:
        """Detect if running inside Sublime Text's terminal.

        Note: Sublime Text does not have a built-in integrated terminal.
        Terminal packages (like Terminus) may be used but don't set
        specific environment variables for detection.
        """
        term_program = _get_term_program()
        return term_program is not None and "sublime" in term_program.lower()
