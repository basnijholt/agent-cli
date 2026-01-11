"""Neovim editor adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Editor

if TYPE_CHECKING:
    from pathlib import Path


class Neovim(Editor):
    """Neovim - Hyperextensible Vim-based text editor."""

    name = "neovim"
    command = "nvim"
    alt_commands = ("neovim",)
    install_url = "https://neovim.io"
    detect_env_vars = ("NVIM",)
    # No detect_term_program - Neovim doesn't set TERM_PROGRAM (uses $NVIM)

    def open_command(self, path: Path) -> list[str]:
        """Return the command to open a directory in Neovim.

        Uses 'cd <path> && nvim .' pattern to ensure neovim's working
        directory is set correctly (matches GTR behavior).
        """
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed"
            raise RuntimeError(msg)
        return ["sh", "-c", f'cd "{path.as_posix()}" && {exe} .']
