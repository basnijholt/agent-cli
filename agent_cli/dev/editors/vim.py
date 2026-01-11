"""Vim editor adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Editor

if TYPE_CHECKING:
    from pathlib import Path


class Vim(Editor):
    """Vim - The ubiquitous text editor.

    Note: Vim does not have an integrated terminal in the traditional sense.
    VIM and VIMRUNTIME env vars are used BY vim to locate runtime files,
    NOT set to indicate running inside vim. Detection always returns False.

    Evidence: https://vimdoc.sourceforge.net/htmldoc/starting.html
    Quote: "The environment variable '$VIM' is used to locate various user
           files for Vim" and "$VIMRUNTIME is used to locate various support
           files, such as the on-line documentation"
    """

    name = "vim"
    command = "vim"
    alt_commands = ("vi",)
    install_url = "https://www.vim.org"
    # No detection - vim has no integrated terminal that sets env vars

    def open_command(self, path: Path) -> list[str]:
        """Return the command to open a directory in Vim.

        Uses 'cd <path> && vim .' pattern to ensure vim's working
        directory is set correctly (matches GTR behavior).
        """
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed"
            raise RuntimeError(msg)
        return ["sh", "-c", f'cd "{path.as_posix()}" && {exe} .']
