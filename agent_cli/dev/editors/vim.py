"""Vim editor adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Editor

if TYPE_CHECKING:
    from pathlib import Path


class Vim(Editor):
    """Vim - The ubiquitous text editor."""

    name = "vim"
    command = "vim"
    alt_commands = ("vi",)
    install_url = "https://www.vim.org"
    detect_env_vars = ("VIM", "VIMRUNTIME")
    # No detect_term_program - vim doesn't set TERM_PROGRAM (uses VIM/VIMRUNTIME)

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
