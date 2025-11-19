"""FastAPI application factory for RAG."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_cli.rag.engine import initial_index, load_hashes_from_metadata, process_chat_request
from agent_cli.rag.indexer import start_watcher
from agent_cli.rag.retriever import get_reranker_model
from agent_cli.rag.store import get_all_metadata, init_collection

if TYPE_CHECKING:
    from pathlib import Path

    from agent_cli.rag.models import ChatRequest

logger = logging.getLogger("agent_cli.rag.api")


def create_app(
    docs_folder: Path,
    chroma_path: Path,
    llama_url: str,
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
    collection = init_collection(chroma_path)
    reranker_model = get_reranker_model()
    file_hashes = load_hashes_from_metadata(collection)
    docs_folder.mkdir(exist_ok=True, parents=True)

    # Start Watcher
    observer = start_watcher(collection, docs_folder, file_hashes)

    # Start Initial Index (in background, maybe we should use asyncio.create_task if inside app startup,
    # but threading is fine for now as in original)
    threading.Thread(
        target=initial_index,
        args=(collection, docs_folder, file_hashes),
    ).start()

    @app.on_event("shutdown")
    def shutdown_event() -> None:
        observer.stop()
        observer.join()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatRequest) -> Any:
        async with httpx.AsyncClient(timeout=120.0) as client:
            return await process_chat_request(
                request,
                collection,
                reranker_model,
                llama_url.rstrip("/"),
                client,
            )

    @app.post("/reindex")
    def reindex_all() -> dict[str, Any]:
        """Manually reindex all files."""
        threading.Thread(
            target=initial_index,
            args=(collection, docs_folder, file_hashes),
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
            "llama_url": llama_url,
        }

    return app
