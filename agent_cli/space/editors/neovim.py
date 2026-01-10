"""Neovim editor adapter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base import Editor, _get_term_program

if TYPE_CHECKING:
    from pathlib import Path


class Neovim(Editor):
    """Neovim - Hyperextensible Vim-based text editor."""

    name = "neovim"
    command = "nvim"
    alt_commands = ("neovim",)
    install_url = "https://neovim.io"

    def detect(self) -> bool:
        """Detect if running inside Neovim's terminal."""
        # Check for Neovim terminal environment
        if os.environ.get("NVIM"):
            return True
        if os.environ.get("NVIM_LISTEN_ADDRESS"):
            return True
        term_program = _get_term_program()
        return term_program is not None and "nvim" in term_program.lower()

    def open_command(self, path: Path) -> list[str]:
        """Return the command to open a directory in Neovim.

        Uses 'cd <path> && nvim .' pattern to ensure neovim's working
        directory is set correctly (matches GTR behavior).
        """
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed"
            raise RuntimeError(msg)
        return ["sh", "-c", f'cd "{path}" && {exe} .']
