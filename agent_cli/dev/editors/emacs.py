"""Emacs editor adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Editor

if TYPE_CHECKING:
    from pathlib import Path


class Emacs(Editor):
    """Emacs - An extensible, customizable text editor.

    Detection via INSIDE_EMACS only. The legacy EMACS env var is deprecated.

    Evidence: https://github.com/emacs-mirror/emacs/blob/master/etc/NEWS.25
    Quote: "'M-x shell' and 'M-x compile' no longer set the EMACS environment
           variable. This avoids clashing when other programs use the variable
           for other purposes. [...] Use the INSIDE_EMACS environment variable
           instead."
    """

    name = "emacs"
    command = "emacs"
    alt_commands = ("emacsclient",)
    install_url = "https://www.gnu.org/software/emacs/"
    detect_env_vars = ("INSIDE_EMACS",)  # EMACS is deprecated since Emacs 25
    # No detect_term_program - Emacs doesn't set TERM_PROGRAM

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
            return [exe, "-n", path.as_posix()]
        # Run standalone emacs in background like GTR does
        return ["sh", "-c", f'{exe} "{path.as_posix()}" &']
