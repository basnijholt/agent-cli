"""Vim editor adapter."""

from __future__ import annotations

import os

from .base import Editor, _get_term_program


class Vim(Editor):
    """Vim - The ubiquitous text editor."""

    name = "vim"
    command = "vim"
    alt_commands = ("vi",)
    install_url = "https://www.vim.org"

    def detect(self) -> bool:
        """Detect if running inside Vim's terminal."""
        # Check for Vim terminal environment
        if os.environ.get("VIM"):
            return True
        if os.environ.get("VIMRUNTIME"):
            return True
        term_program = _get_term_program()
        return term_program is not None and term_program.lower() == "vim"
