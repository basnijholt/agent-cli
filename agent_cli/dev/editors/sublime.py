"""Sublime Text editor adapter."""

from __future__ import annotations

import os

from .base import Editor, _get_term_program


class SublimeText(Editor):
    """Sublime Text - A sophisticated text editor for code."""

    name = "sublime"
    command = "subl"
    alt_commands = ("sublime_text", "sublime")
    install_url = "https://www.sublimetext.com"

    def detect(self) -> bool:
        """Detect if running inside Sublime Text's terminal."""
        # Sublime doesn't typically have an integrated terminal
        # but check for any environment variables
        term_program = _get_term_program()
        if term_program and "sublime" in term_program.lower():
            return True
        return os.environ.get("SUBLIME_SESSION") is not None
