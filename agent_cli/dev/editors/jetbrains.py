"""JetBrains IDE editor adapters."""

from __future__ import annotations

import os

from .base import Editor


class _JetBrainsEditor(Editor):
    """Base class for JetBrains IDEs with common detection logic."""

    def detect(self) -> bool:
        """Detect if running inside a JetBrains IDE's terminal.

        JetBrains IDEs set TERMINAL_EMULATOR=JetBrains-JediTerm.
        Source: https://github.com/JetBrains/jediterm/issues/253
        """
        return os.environ.get("TERMINAL_EMULATOR") == "JetBrains-JediTerm"


class IntelliJIdea(_JetBrainsEditor):
    """IntelliJ IDEA - The IDE for Java and other languages."""

    name = "idea"
    command = "idea"
    install_url = "https://www.jetbrains.com/idea/"


class PyCharm(_JetBrainsEditor):
    """PyCharm - The Python IDE for Professional Developers."""

    name = "pycharm"
    command = "pycharm"
    alt_commands = ("charm",)
    install_url = "https://www.jetbrains.com/pycharm/"


class WebStorm(_JetBrainsEditor):
    """WebStorm - The JavaScript and TypeScript IDE."""

    name = "webstorm"
    command = "webstorm"
    install_url = "https://www.jetbrains.com/webstorm/"


class GoLand(_JetBrainsEditor):
    """GoLand - The IDE for Go developers."""

    name = "goland"
    command = "goland"
    install_url = "https://www.jetbrains.com/go/"


class RustRover(_JetBrainsEditor):
    """RustRover - The IDE for Rust developers."""

    name = "rustrover"
    command = "rustrover"
    install_url = "https://www.jetbrains.com/rust/"
