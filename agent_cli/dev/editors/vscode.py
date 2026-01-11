"""VS Code editor adapter."""

from __future__ import annotations

from .base import Editor


class VSCode(Editor):
    """Visual Studio Code editor."""

    name = "vscode"
    command = "code"
    alt_commands = ("code-insiders",)
    install_url = "https://code.visualstudio.com"
    detect_term_program = "vscode"
