"""Nano editor adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Editor

if TYPE_CHECKING:
    from pathlib import Path


class Nano(Editor):
    """Nano - Simple terminal text editor."""

    name = "nano"
    command = "nano"
    install_url = "https://www.nano-editor.org"
    # Nano has no integrated terminal, detection always returns False (default)

    def open_command(self, path: Path) -> list[str]:
        """Return the command to open a directory in Nano.

        Uses 'cd <path> && nano .' pattern to ensure nano's working
        directory is set correctly.
        """
        exe = self.get_executable()
        if exe is None:
            msg = f"{self.name} is not installed"
            raise RuntimeError(msg)
        return ["sh", "-c", f'cd "{path}" && {exe} .']
