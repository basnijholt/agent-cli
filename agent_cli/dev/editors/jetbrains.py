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


def _create_jetbrains_editor(
    name: str,
    command: str,
    install_url: str,
    alt_commands: tuple[str, ...] = (),
) -> type[_JetBrainsEditor]:
    """Factory to create JetBrains editor classes with minimal boilerplate."""

    class _Editor(_JetBrainsEditor):
        pass

    _Editor.name = name
    _Editor.command = command
    _Editor.alt_commands = alt_commands
    _Editor.install_url = install_url
    _Editor.__name__ = name.replace("-", "_").title().replace("_", "")
    _Editor.__qualname__ = _Editor.__name__
    return _Editor


# JetBrains IDE definitions: (name, command, url, alt_commands)
_JETBRAINS_IDES = [
    ("idea", "idea", "https://www.jetbrains.com/idea/", ()),
    ("pycharm", "pycharm", "https://www.jetbrains.com/pycharm/", ("charm",)),
    ("webstorm", "webstorm", "https://www.jetbrains.com/webstorm/", ()),
    ("goland", "goland", "https://www.jetbrains.com/go/", ()),
    ("rustrover", "rustrover", "https://www.jetbrains.com/rust/", ()),
]

# Generate editor classes
IntelliJIdea = _create_jetbrains_editor(*_JETBRAINS_IDES[0])
PyCharm = _create_jetbrains_editor(*_JETBRAINS_IDES[1])
WebStorm = _create_jetbrains_editor(*_JETBRAINS_IDES[2])
GoLand = _create_jetbrains_editor(*_JETBRAINS_IDES[3])
RustRover = _create_jetbrains_editor(*_JETBRAINS_IDES[4])
