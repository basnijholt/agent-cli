"""Emacs editor adapter."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base import Editor, _get_term_program

if TYPE_CHECKING:
    from pathlib import Path


class Emacs(Editor):
    """Emacs - An extensible, customizable text editor."""

    name = "emacs"
    command = "emacs"
    alt_commands = ("emacsclient",)
    install_url = "https://www.gnu.org/software/emacs/"

    def detect(self) -> bool:
        """Detect if running inside Emacs' terminal."""
        # Check for Emacs terminal environment
        if os.environ.get("INSIDE_EMACS"):
            return True
        if os.environ.get("EMACS"):
            return True
        term_program = _get_term_program()
        return term_program is not None and "emacs" in term_program.lower()

    def open_command(self, path: Path) -> list[str]:
        """Return the command to open a directory in Emacs.

        Uses background mode (&) for standalone emacs to match GTR behavior.
        emacsclient uses -n flag which already runs in background.
        """
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed"
            raise RuntimeError(msg)
        # Use emacsclient if available for faster opening (-n = don't wait)
        if "emacsclient" in exe:
            return [exe, "-n", str(path)]
        # Run standalone emacs in background like GTR does
        return ["sh", "-c", f'{exe} "{path}" &']
