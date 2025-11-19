"""FastAPI application factory for RAG."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
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
) -> FastAPI:
    """Create the FastAPI app."""
    app = FastAPI(title="RAG Proxy")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize State
    logger.info("Initializing RAG components...")

    logger.info("Loading vector database (ChromaDB)...")
    collection = init_collection(chroma_path)

    logger.info("Loading reranker model (CrossEncoder)...")
    reranker_model = get_reranker_model()

    logger.info("Loading existing file index...")
    file_hashes = load_hashes_from_metadata(collection)
    logger.info("Loaded %d files from index.", len(file_hashes))

    docs_folder.mkdir(exist_ok=True, parents=True)

    # Background Tasks
    background_tasks = set()

    @app.on_event("startup")
    async def startup_event() -> None:
        logger.info("Starting file watcher...")
        watcher_task = asyncio.create_task(watch_docs(collection, docs_folder, file_hashes))
        background_tasks.add(watcher_task)
        watcher_task.add_done_callback(background_tasks.discard)

        logger.info("Starting initial index scan...")
        threading.Thread(
            target=initial_index,
            args=(collection, docs_folder, file_hashes),
            daemon=True,
        ).start()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatRequest) -> Any:
        return await process_chat_request(
            request,
            collection,
            reranker_model,
            openai_base_url.rstrip("/"),
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
        }

    return app
