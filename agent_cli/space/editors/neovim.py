"""Neovim editor adapter."""

from __future__ import annotations

import os

from .base import Editor, _get_term_program


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
