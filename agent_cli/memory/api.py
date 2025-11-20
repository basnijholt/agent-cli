"""FastAPI application factory for memory server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agent_cli.memory.engine import process_chat_request
from agent_cli.memory.models import ChatRequest  # noqa: TC001
from agent_cli.memory.store import init_memory_collection

if TYPE_CHECKING:
    from pathlib import Path

LOGGER = logging.getLogger("agent_cli.memory.api")


def create_app(
    memory_path: Path,
    openai_base_url: str,
    embedding_model: str = "text-embedding-3-small",
    embedding_api_key: str | None = None,
    chat_api_key: str | None = None,
    default_top_k: int = 5,
    enable_summarization: bool = True,
    max_entries: int = 500,
) -> FastAPI:
    """Create the FastAPI app for memory-backed chat."""
    LOGGER.info("Initializing memory components...")

    LOGGER.info("Loading memory collection (ChromaDB)...")
    collection = init_memory_collection(
        memory_path,
        embedding_model=embedding_model,
        openai_base_url=openai_base_url,
        openai_api_key=embedding_api_key,
    )

    app = FastAPI(title="Memory Proxy")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request, chat_request: ChatRequest) -> Any:
        auth_header = request.headers.get("Authorization")
        api_key = None
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header.split(" ")[1]

        if not api_key:
            api_key = chat_api_key

        return await process_chat_request(
            chat_request,
            collection,
            openai_base_url.rstrip("/"),
            default_top_k=default_top_k,
            api_key=api_key,
            enable_summarization=enable_summarization,
            max_entries=max_entries,
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "memory_store": str(memory_path),
            "openai_base_url": openai_base_url,
            "embedding_model": embedding_model,
            "default_top_k": str(default_top_k),
        }

    return app
