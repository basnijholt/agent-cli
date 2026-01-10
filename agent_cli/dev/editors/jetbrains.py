"""JetBrains IDE editor adapters."""

from __future__ import annotations

import os

from .base import Editor, _get_term_program


class IntelliJIdea(Editor):
    """IntelliJ IDEA - The IDE for Java and other languages."""

    name = "idea"
    command = "idea"
    alt_commands = ()
    install_url = "https://www.jetbrains.com/idea/"

    def detect(self) -> bool:
        """Detect if running inside IntelliJ IDEA's terminal."""
        term_program = _get_term_program()
        if term_program and "idea" in term_program.lower():
            return True
        # Check for JetBrains terminal environment
        return os.environ.get("TERMINAL_EMULATOR") == "JetBrains-JediTerm"


class PyCharm(Editor):
    """PyCharm - The Python IDE for Professional Developers."""

    name = "pycharm"
    command = "pycharm"
    alt_commands = ("charm",)
    install_url = "https://www.jetbrains.com/pycharm/"

    def detect(self) -> bool:
        """Detect if running inside PyCharm's terminal."""
        term_program = _get_term_program()
        if term_program and "pycharm" in term_program.lower():
            return True
        # Check for JetBrains terminal environment
        terminal_emulator = os.environ.get("TERMINAL_EMULATOR", "")
        return terminal_emulator == "JetBrains-JediTerm"


class WebStorm(Editor):
    """WebStorm - The JavaScript and TypeScript IDE."""

    name = "webstorm"
    command = "webstorm"
    alt_commands = ()
    install_url = "https://www.jetbrains.com/webstorm/"

    def detect(self) -> bool:
        """Detect if running inside WebStorm's terminal."""
        term_program = _get_term_program()
        if term_program and "webstorm" in term_program.lower():
            return True
        # Check for JetBrains terminal environment
        return os.environ.get("TERMINAL_EMULATOR") == "JetBrains-JediTerm"


class GoLand(Editor):
    """GoLand - The IDE for Go developers."""

    name = "goland"
    command = "goland"
    alt_commands = ()
    install_url = "https://www.jetbrains.com/go/"

    def detect(self) -> bool:
        """Detect if running inside GoLand's terminal."""
        term_program = _get_term_program()
        if term_program and "goland" in term_program.lower():
            return True
        return os.environ.get("TERMINAL_EMULATOR") == "JetBrains-JediTerm"


class RustRover(Editor):
    """RustRover - The IDE for Rust developers."""

    name = "rustrover"
    command = "rustrover"
    alt_commands = ()
    install_url = "https://www.jetbrains.com/rust/"

    def detect(self) -> bool:
        """Detect if running inside RustRover's terminal."""
        term_program = _get_term_program()
        if term_program and "rustrover" in term_program.lower():
            return True
        return os.environ.get("TERMINAL_EMULATOR") == "JetBrains-JediTerm"
