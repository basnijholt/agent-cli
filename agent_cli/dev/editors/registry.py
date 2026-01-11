"""Registry for editor adapters."""

from __future__ import annotations

from agent_cli.dev.registry import Registry

from .base import Editor  # noqa: TC001
from .cursor import Cursor
from .emacs import Emacs
from .jetbrains import GoLand, IntelliJIdea, PyCharm, RustRover, WebStorm
from .nano import Nano
from .neovim import Neovim
from .sublime import SublimeText
from .vim import Vim
from .vscode import VSCode
from .zed import Zed

# All available editors (in priority order for detection)
_EDITORS: list[type[Editor]] = [
    # Modern AI-focused editors first
    Cursor,
    VSCode,
    Zed,
    # JetBrains IDEs
    PyCharm,
    IntelliJIdea,
    WebStorm,
    GoLand,
    RustRover,
    # Terminal editors
    Neovim,
    Vim,
    Nano,
    Emacs,
    # Other GUI editors
    SublimeText,
]

_registry: Registry[Editor] = Registry(_EDITORS)


def get_all_editors() -> list[Editor]:
    """Get instances of all registered editors."""
    return _registry.get_all()


def get_available_editors() -> list[Editor]:
    """Get all installed/available editors."""
    return _registry.get_available()


def detect_current_editor() -> Editor | None:
    """Detect which editor's integrated terminal we're running in."""
    return _registry.detect_current()


def get_editor(name: str) -> Editor | None:
    """Get an editor by name."""
    return _registry.get_by_name(name)
