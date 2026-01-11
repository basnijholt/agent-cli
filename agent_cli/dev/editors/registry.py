"""Registry for editor adapters."""

from __future__ import annotations

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

# Cache for editor instances
_editor_instances: dict[str, Editor] = {}


def get_all_editors() -> list[Editor]:
    """Get instances of all registered editors."""
    editors = []
    for editor_cls in _EDITORS:
        name = editor_cls.name
        if name not in _editor_instances:
            _editor_instances[name] = editor_cls()
        editors.append(_editor_instances[name])
    return editors


def get_available_editors() -> list[Editor]:
    """Get all installed/available editors."""
    return [editor for editor in get_all_editors() if editor.is_available()]


def detect_current_editor() -> Editor | None:
    """Detect which editor's integrated terminal we're running in."""
    for editor in get_all_editors():
        if editor.detect():
            return editor
    return None


def get_editor(name: str) -> Editor | None:
    """Get an editor by name."""
    name_lower = name.lower()
    for editor in get_all_editors():
        if editor.name.lower() == name_lower:
            return editor
        if editor.command.lower() == name_lower:
            return editor
    return None
