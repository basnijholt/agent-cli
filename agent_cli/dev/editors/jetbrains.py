"""JetBrains IDE editor adapters."""

from __future__ import annotations

import os

from .base import Editor, _get_term_program


class _JetBrainsEditor(Editor):
    """Base class for JetBrains IDEs with common detection logic."""

    def detect(self) -> bool:
        """Detect if running inside a JetBrains IDE's terminal.

        JetBrains IDEs set TERMINAL_EMULATOR=JetBrains-JediTerm.
        Also checks TERM_PROGRAM for the specific IDE name.
        """
        # Check for JetBrains terminal environment (shared across all JetBrains IDEs)
        if os.environ.get("TERMINAL_EMULATOR") == "JetBrains-JediTerm":
            return True
        # Check TERM_PROGRAM for specific IDE
        if self.detect_term_program:
            term_program = _get_term_program()
            if term_program and self.detect_term_program.lower() in term_program.lower():
                return True
        return False


class IntelliJIdea(_JetBrainsEditor):
    """IntelliJ IDEA - The IDE for Java and other languages."""

    name = "idea"
    command = "idea"
    install_url = "https://www.jetbrains.com/idea/"
    detect_term_program = "idea"


class PyCharm(_JetBrainsEditor):
    """PyCharm - The Python IDE for Professional Developers."""

    name = "pycharm"
    command = "pycharm"
    alt_commands = ("charm",)
    install_url = "https://www.jetbrains.com/pycharm/"
    detect_term_program = "pycharm"


class WebStorm(_JetBrainsEditor):
    """WebStorm - The JavaScript and TypeScript IDE."""

    name = "webstorm"
    command = "webstorm"
    install_url = "https://www.jetbrains.com/webstorm/"
    detect_term_program = "webstorm"


class GoLand(_JetBrainsEditor):
    """GoLand - The IDE for Go developers."""

    name = "goland"
    command = "goland"
    install_url = "https://www.jetbrains.com/go/"
    detect_term_program = "goland"


class RustRover(_JetBrainsEditor):
    """RustRover - The IDE for Rust developers."""

    name = "rustrover"
    command = "rustrover"
    install_url = "https://www.jetbrains.com/rust/"
    detect_term_program = "rustrover"
