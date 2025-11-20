"""Memory module powered by Letta."""

from __future__ import annotations

from importlib.util import find_spec

_REQUIRED_DEPS = {
    "letta": "letta",
    "chromadb": "chromadb",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
}

_MISSING = [
    pkg_name for module_name, pkg_name in _REQUIRED_DEPS.items() if find_spec(module_name) is None
]

if _MISSING:
    msg = (
        f"Missing required dependencies for memory support: {', '.join(_MISSING)}. "
        "Please install with `pip install agent-cli[memory]` or `uv sync --extra memory`."
    )
    raise ImportError(msg)
