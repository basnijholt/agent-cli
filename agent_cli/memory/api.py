"""FastAPI application factory for memory proxy."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agent_cli.constants import DEFAULT_OPENAI_EMBEDDING_MODEL
from agent_cli.core.openai_proxy import proxy_request_to_upstream
from agent_cli.memory.client import MemoryClient
from agent_cli.memory.models import ChatRequest  # noqa: TC001

if TYPE_CHECKING:
    from pathlib import Path

LOGGER = logging.getLogger(__name__)


def create_app(
    memory_path: Path,
    openai_base_url: str,
    embedding_model: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
    embedding_api_key: str | None = None,
    chat_api_key: str | None = None,
    default_top_k: int = 5,
    enable_summarization: bool = True,
    max_entries: int = 500,
    mmr_lambda: float = 0.7,
    recency_weight: float = 0.2,
    score_threshold: float | None = None,
    enable_git_versioning: bool = True,
) -> FastAPI:
    """Create the FastAPI app for memory-backed chat."""
    LOGGER.info("Initializing memory client...")

    client = MemoryClient(
        memory_path=memory_path,
        openai_base_url=openai_base_url,
        embedding_model=embedding_model,
        embedding_api_key=embedding_api_key,
        chat_api_key=chat_api_key,
        default_top_k=default_top_k,
        enable_summarization=enable_summarization,
        max_entries=max_entries,
        mmr_lambda=mmr_lambda,
        recency_weight=recency_weight,
        score_threshold=score_threshold,
        start_watcher=False,  # We control start/stop via app events
        enable_git_versioning=enable_git_versioning,
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

        return await client.chat(
            messages=chat_request.messages,
            conversation_id=chat_request.memory_id or "default",
            model=chat_request.model,
            stream=chat_request.stream or False,
            api_key=api_key,
            memory_top_k=chat_request.memory_top_k,
            recency_weight=chat_request.memory_recency_weight,
            score_threshold=chat_request.memory_score_threshold,
        )

    @app.on_event("startup")
    async def start_watch() -> None:
        client.start()

    @app.on_event("shutdown")
    async def stop_watch() -> None:
        await client.stop()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "memory_store": str(client.memory_path),
            "openai_base_url": client.openai_base_url,
            "default_top_k": str(client.default_top_k),
        }

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    )
    async def proxy_catch_all(request: Request, path: str) -> Any:
        """Forward any other request to the upstream provider."""
        return await proxy_request_to_upstream(
            request,
            path,
            client.openai_base_url,
            client.chat_api_key,
        )

    return app
