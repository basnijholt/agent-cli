"""Memory module powered by Letta."""

from __future__ import annotations

from agent_cli.core.deps import ensure_optional_dependencies

_REQUIRED_DEPS = {
    "letta": "letta",
    "chromadb": "chromadb",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
}

ensure_optional_dependencies(
    _REQUIRED_DEPS,
    extra_name="memory",
    install_hint="`pip install agent-cli[memory]` or `uv sync --extra memory`",
)
