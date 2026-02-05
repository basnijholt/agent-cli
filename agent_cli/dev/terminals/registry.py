"""Registry for terminal adapters."""

from __future__ import annotations

from agent_cli.dev.registry import Registry

from .apple_terminal import AppleTerminal
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
    AppleTerminal,
    GnomeTerminal,
]

_registry: Registry[Terminal] = Registry(_TERMINALS)


def get_all_terminals() -> list[Terminal]:
    """Get instances of all registered terminals."""
    return _registry.get_all()


def get_available_terminals() -> list[Terminal]:
    """Get all installed/available terminals."""
    return _registry.get_available()


def detect_current_terminal() -> Terminal | None:
    """Detect which terminal we're running in."""
    return _registry.detect_current()


def get_terminal(name: str) -> Terminal | None:
    """Get a terminal by name."""
    return _registry.get_by_name(name)
