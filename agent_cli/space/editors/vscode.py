"""VS Code editor adapter."""

from __future__ import annotations

from .base import Editor, _get_term_program


class VSCode(Editor):
    """Visual Studio Code editor."""

    name = "vscode"
    command = "code"
    alt_commands = ("code-insiders",)
    install_url = "https://code.visualstudio.com"

    def detect(self) -> bool:
        """Detect if running inside VS Code's integrated terminal."""
        term_program = _get_term_program()
        return term_program is not None and "vscode" in term_program.lower()
