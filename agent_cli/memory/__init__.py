"""Memory module for long-term chat history."""

from __future__ import annotations

from agent_cli.core.deps import ensure_optional_dependencies

_REQUIRED_DEPS = {
    "chromadb": "chromadb",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "onnxruntime": "onnxruntime",
    "huggingface_hub": "huggingface-hub",
    "transformers": "transformers",
}

ensure_optional_dependencies(
    _REQUIRED_DEPS,
    extra_name="memory",
    install_hint="`pip install agent-cli[memory]` or `uv sync --extra memory`",
)

from agent_cli.memory.client import MemoryClient  # noqa: E402

__all__ = ["MemoryClient"]
