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
    score_threshold: float = 0.35,
    enable_git_versioning: bool = True,
    # Long conversation mode settings
    long_conversation: bool = False,
    context_budget: int = 150_000,
    compress_threshold: float = 0.8,
    raw_recent_tokens: int = 40_000,
) -> FastAPI:
    """Create the FastAPI app for memory-backed chat."""
    app = FastAPI(title="Memory Proxy")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store config in app state for access in endpoints
    app.state.memory_path = memory_path
    app.state.openai_base_url = openai_base_url
    app.state.chat_api_key = chat_api_key
    app.state.long_conversation = long_conversation
    app.state.context_budget = context_budget
    app.state.compress_threshold = compress_threshold
    app.state.raw_recent_tokens = raw_recent_tokens

    # Only initialize MemoryClient for standard mode
    client: MemoryClient | None = None
    if not long_conversation:
        LOGGER.info("Initializing memory client (standard mode)...")
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
            start_watcher=False,
            enable_git_versioning=enable_git_versioning,
        )
        app.state.client = client
    else:
        LOGGER.info("Long conversation mode enabled, skipping standard memory client")
        app.state.client = None

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request, chat_request: ChatRequest) -> Any:
        auth_header = request.headers.get("Authorization")
        api_key = None
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header.split(" ")[1]

        if app.state.long_conversation:
            # Long conversation mode
            from agent_cli.memory._long_conversation import (  # noqa: PLC0415
                process_long_conversation_chat,
            )

            return await process_long_conversation_chat(
                memory_root=app.state.memory_path,
                conversation_id=chat_request.memory_id or "default",
                messages=[m.model_dump() for m in chat_request.messages],
                model=chat_request.model,
                openai_base_url=app.state.openai_base_url,
                api_key=api_key or app.state.chat_api_key,
                stream=chat_request.stream or False,
                target_context_tokens=app.state.context_budget,
                compress_threshold=app.state.compress_threshold,
                raw_recent_tokens=app.state.raw_recent_tokens,
            )

        # Standard memory mode
        memory_client = app.state.client
        return await memory_client.chat(
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
        if app.state.client:
            app.state.client.start()

    @app.on_event("shutdown")
    async def stop_watch() -> None:
        if app.state.client:
            await app.state.client.stop()

    @app.get("/health")
    def health() -> dict[str, str]:
        result = {
            "status": "ok",
            "memory_store": str(app.state.memory_path),
            "openai_base_url": app.state.openai_base_url,
            "mode": "long_conversation" if app.state.long_conversation else "standard",
        }
        if app.state.client:
            result["default_top_k"] = str(app.state.client.default_top_k)
        return result

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    )
    async def proxy_catch_all(request: Request, path: str) -> Any:
        """Forward any other request to the upstream provider."""
        return await proxy_request_to_upstream(
            request,
            path,
            app.state.openai_base_url,
            app.state.chat_api_key,
        )

    return app
