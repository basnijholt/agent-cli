"""Helpers for optional dependency checks."""

from __future__ import annotations

import sys
from importlib.util import find_spec

# Dependencies that don't support Python 3.14 yet
_PYTHON_314_INCOMPATIBLE = {"chromadb", "onnxruntime"}


def ensure_optional_dependencies(
    required: dict[str, str],
    *,
    extra_name: str,
    install_hint: str | None = None,
) -> None:
    """Ensure optional dependencies are present, otherwise raise ImportError."""
    missing = [
        pkg_name for module_name, pkg_name in required.items() if find_spec(module_name) is None
    ]
    if not missing:
        return

    # Check if running on Python 3.14+ with incompatible dependencies
    is_py314 = sys.version_info >= (3, 14)
    incompatible = set(missing) & _PYTHON_314_INCOMPATIBLE

    if is_py314 and incompatible:
        msg = (
            f"The '{extra_name}' feature requires {', '.join(sorted(incompatible))}, "
            f"which {'does' if len(incompatible) == 1 else 'do'} not support Python 3.14 yet. "
            f"Please use Python 3.13 or earlier for this feature."
        )
        raise ImportError(msg)

    hint = install_hint or f"`pip install agent-cli[{extra_name}]`"
    msg = f"Missing required dependencies for {extra_name}: {', '.join(missing)}. Please install with {hint}."
    raise ImportError(msg)
