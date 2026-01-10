"""Registry for terminal adapters."""

from __future__ import annotations

from .base import Terminal  # noqa: TC001
from .gnome import GnomeTerminal
from .iterm2 import ITerm2
from .kitty import Kitty
from .tmux import Tmux
from .warp import Warp
from .zellij import Zellij

# All available terminals (in priority order for detection)
# Terminal multiplexers first (tmux, zellij) as they run inside other terminals
_TERMINALS: list[type[Terminal]] = [
    Tmux,
    Zellij,
    ITerm2,
    Kitty,
    Warp,
    GnomeTerminal,
]

# Cache for terminal instances
_terminal_instances: dict[str, Terminal] = {}


def get_all_terminals() -> list[Terminal]:
    """Get instances of all registered terminals."""
    terminals = []
    for terminal_cls in _TERMINALS:
        name = terminal_cls.name
        if name not in _terminal_instances:
            _terminal_instances[name] = terminal_cls()
        terminals.append(_terminal_instances[name])
    return terminals


def get_available_terminals() -> list[Terminal]:
    """Get all installed/available terminals."""
    return [terminal for terminal in get_all_terminals() if terminal.is_available()]


def detect_current_terminal() -> Terminal | None:
    """Detect which terminal we're running in."""
    for terminal in get_all_terminals():
        if terminal.detect():
            return terminal
    return None


def get_terminal(name: str) -> Terminal | None:
    """Get a terminal by name."""
    name_lower = name.lower()
    for terminal in get_all_terminals():
        if terminal.name.lower() == name_lower:
            return terminal
    return None
