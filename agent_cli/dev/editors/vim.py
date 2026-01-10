"""Vim editor adapter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base import Editor, _get_term_program

if TYPE_CHECKING:
    from pathlib import Path


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

    def open_command(self, path: Path) -> list[str]:
        """Return the command to open a directory in Vim.

        Uses 'cd <path> && vim .' pattern to ensure vim's working
        directory is set correctly (matches GTR behavior).
        """
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed"
            raise RuntimeError(msg)
        return ["sh", "-c", f'cd "{path}" && {exe} .']
