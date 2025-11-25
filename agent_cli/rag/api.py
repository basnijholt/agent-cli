"""FastAPI application factory for RAG."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agent_cli.constants import DEFAULT_OPENAI_EMBEDDING_MODEL
from agent_cli.core.openai_proxy import proxy_request_to_upstream
from agent_cli.rag.client import RagClient
from agent_cli.rag.models import ChatRequest  # noqa: TC001

if TYPE_CHECKING:
    from pathlib import Path

LOGGER = logging.getLogger(__name__)


def create_app(
    docs_folder: Path,
    chroma_path: Path,
    openai_base_url: str,
    embedding_model: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
    embedding_api_key: str | None = None,
    chat_api_key: str | None = None,
    limit: int = 3,
    enable_rag_tools: bool = True,
) -> FastAPI:
    """Create the FastAPI app."""
    LOGGER.info("Initializing RAG client...")

    client = RagClient(
        docs_folder=docs_folder,
        chroma_path=chroma_path,
        openai_base_url=openai_base_url,
        embedding_model=embedding_model,
        embedding_api_key=embedding_api_key,
        chat_api_key=chat_api_key,
        default_top_k=limit,
        enable_rag_tools=enable_rag_tools,
        start_watcher=False,  # Control via lifespan
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # noqa: ANN202
        LOGGER.info("Starting RAG client...")
        client.start()
        yield
        LOGGER.info("Stopping RAG client...")
        await client.stop()

    app = FastAPI(title="RAG Proxy", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request, chat_request: ChatRequest) -> Any:
        # Extract API Key from Authorization header if present
        auth_header = request.headers.get("Authorization")
        api_key = None
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header.split(" ")[1]

        # Use process_request to preserve extra fields in the ChatRequest
        return await client.process_request(chat_request, api_key=api_key)

    @app.post("/reindex")
    def reindex_all() -> dict[str, Any]:
        """Manually reindex all files."""
        client.reindex(blocking=False)
        return {"status": "started reindexing", "total_chunks": client.collection.count()}

    @app.get("/files")
    def list_files() -> dict[str, Any]:
        """List all indexed files."""
        files = client.list_files()
        return {"files": files, "total": len(files)}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "rag_docs": str(client.docs_folder),
            "openai_base_url": client.openai_base_url,
            "total_files": str(len(client.file_hashes)),
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
