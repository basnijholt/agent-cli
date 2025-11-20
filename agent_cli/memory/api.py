"""FastAPI application factory for memory server."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agent_cli.memory.engine import process_chat_request
from agent_cli.memory.files import ensure_store_dirs
from agent_cli.memory.indexer import MemoryIndex, initial_index, watch_memory_store
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
    mmr_lambda: float = 0.7,
) -> FastAPI:
    """Create the FastAPI app for memory-backed chat."""
    LOGGER.info("Initializing memory components...")

    memory_path = memory_path.resolve()
    entries_dir, snapshot_path = ensure_store_dirs(memory_path)

    LOGGER.info("Loading memory collection (ChromaDB)...")
    collection = init_memory_collection(
        memory_path,
        embedding_model=embedding_model,
        openai_base_url=openai_base_url,
        openai_api_key=embedding_api_key,
    )

    index = MemoryIndex.from_snapshot(snapshot_path)
    initial_index(collection, memory_path, index=index)

    from agent_cli.rag.retriever import get_reranker_model  # noqa: PLC0415

    reranker_model = get_reranker_model()

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
            memory_path,
            openai_base_url.rstrip("/"),
            reranker_model,
            default_top_k=default_top_k,
            api_key=api_key,
            enable_summarization=enable_summarization,
            max_entries=max_entries,
            mmr_lambda=mmr_lambda,
        )

    watch_task: asyncio.Task | None = None

    @app.on_event("startup")
    async def start_watch() -> None:
        nonlocal watch_task
        watch_task = asyncio.create_task(watch_memory_store(collection, memory_path, index=index))

    @app.on_event("shutdown")
    async def stop_watch() -> None:
        if watch_task:
            watch_task.cancel()
            with suppress(asyncio.CancelledError):
                await watch_task

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "memory_store": str(memory_path),
            "entries_dir": str(entries_dir),
            "openai_base_url": openai_base_url,
            "embedding_model": embedding_model,
            "default_top_k": str(default_top_k),
        }

    return app
