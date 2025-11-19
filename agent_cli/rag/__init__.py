"""RAG module."""

from __future__ import annotations

from importlib.util import find_spec

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

_MISSING = [
    pkg_name for module_name, pkg_name in _REQUIRED_DEPS.items() if find_spec(module_name) is None
]

if _MISSING:
    msg = (
        f"Missing required dependencies for RAG: {', '.join(_MISSING)}. "
        "Please install with `pip install agent-cli[rag]`."
    )
    raise ImportError(msg)

from . import (  # noqa: E402
    api,
    engine,
    indexer,
    models,
    retriever,
    store,
    utils,
)

__all__ = [
    "api",
    "engine",
    "indexer",
    "models",
    "retriever",
    "store",
    "utils",
]
