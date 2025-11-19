"""FastAPI application factory for RAG."""

from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from agent_cli.rag.engine import process_chat_request
from agent_cli.rag.indexer import watch_docs
from agent_cli.rag.indexing import initial_index, load_hashes_from_metadata
from agent_cli.rag.models import ChatRequest  # noqa: TC001
from agent_cli.rag.retriever import get_reranker_model
from agent_cli.rag.store import get_all_metadata, init_collection

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("agent_cli.rag.api")


def create_app(
    docs_folder: Path,
    chroma_path: Path,
    openai_base_url: str,
    embedding_model: str = "text-embedding-3-small",
    embedding_api_key: str | None = None,
    chat_api_key: str | None = None,
    limit: int = 3,
) -> FastAPI:
    """Create the FastAPI app."""
    # Initialize State
    logger.info("Initializing RAG components...")

    logger.info("Loading vector database (ChromaDB)...")
    collection = init_collection(
        chroma_path,
        embedding_model=embedding_model,
        openai_base_url=openai_base_url,
        openai_api_key=embedding_api_key,
    )

    logger.info("Loading reranker model (CrossEncoder)...")
    reranker_model = get_reranker_model()

    logger.info("Loading existing file index...")
    file_hashes = load_hashes_from_metadata(collection)
    logger.info("Loaded %d files from index.", len(file_hashes))

    docs_folder.mkdir(exist_ok=True, parents=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # noqa: ANN202
        logger.info("Starting file watcher...")
        # Background Tasks
        background_tasks = set()
        watcher_task = asyncio.create_task(watch_docs(collection, docs_folder, file_hashes))
        background_tasks.add(watcher_task)
        watcher_task.add_done_callback(background_tasks.discard)

        logger.info("Starting initial index scan...")
        threading.Thread(
            target=initial_index,
            args=(collection, docs_folder, file_hashes),
            daemon=True,
        ).start()
        yield
        # Cleanup if needed
        watcher_task.cancel()
        with suppress(asyncio.CancelledError):
            await watcher_task

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

        # Fallback to server-configured key
        if not api_key:
            api_key = chat_api_key

        return await process_chat_request(
            chat_request,
            collection,
            reranker_model,
            openai_base_url.rstrip("/"),
            default_top_k=limit,
            api_key=api_key,
        )

    @app.post("/reindex")
    def reindex_all() -> dict[str, Any]:
        """Manually reindex all files."""
        logger.info("Manual reindex requested.")
        threading.Thread(
            target=initial_index,
            args=(collection, docs_folder, file_hashes),
            daemon=True,
        ).start()
        return {"status": "started reindexing", "total_chunks": collection.count()}

    @app.get("/files")
    def list_files() -> dict[str, Any]:
        """List all indexed files."""
        metadatas = get_all_metadata(collection)

        files = {}
        for meta in metadatas:
            fp = meta.get("file_path")
            if not fp:
                continue

            if fp not in files:
                files[fp] = {
                    "name": meta.get("source"),
                    "path": fp,
                    "type": meta.get("file_type"),
                    "chunks": 0,
                    "indexed_at": meta.get("indexed_at"),
                }
            files[fp]["chunks"] += 1

        return {"files": list(files.values()), "total": len(files)}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "rag_docs": str(docs_folder),
            "openai_base_url": openai_base_url,
            "embedding_model": embedding_model,
            "limit": str(limit),
        }

    return app
