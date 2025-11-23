"""RAG module."""

from __future__ import annotations

from agent_cli.core.deps import ensure_optional_dependencies

_REQUIRED_DEPS = {
    "chromadb": "chromadb",
    "watchfiles": "watchfiles",
    "markitdown": "markitdown",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "onnxruntime": "onnxruntime",
    "huggingface_hub": "huggingface-hub",
    "transformers": "transformers",
}

ensure_optional_dependencies(
    _REQUIRED_DEPS,
    extra_name="rag",
    install_hint="`pip install agent-cli[rag]` or `uv sync --extra rag`",
)
