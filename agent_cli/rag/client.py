"""High-level client for interacting with the RAG system."""

from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from agent_cli.constants import DEFAULT_OPENAI_EMBEDDING_MODEL
from agent_cli.core.chroma import init_collection
from agent_cli.rag._indexer import watch_docs
from agent_cli.rag._indexing import initial_index, load_hashes_from_metadata
from agent_cli.rag._retriever import get_reranker_model
from agent_cli.rag._store import get_all_metadata
from agent_cli.rag.engine import process_chat_request

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

    from agent_cli.rag._retriever import OnnxCrossEncoder
    from agent_cli.rag.models import ChatRequest

logger = logging.getLogger("agent_cli.rag.client")


class RagClient:
    """A client for interacting with the RAG system.

    This class decouples the RAG logic from the HTTP server, allowing
    direct usage in other applications or scripts.
    """

    def __init__(
        self,
        docs_folder: Path,
        chroma_path: Path,
        openai_base_url: str,
        embedding_model: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
        embedding_api_key: str | None = None,
        chat_api_key: str | None = None,
        default_top_k: int = 3,
        enable_rag_tools: bool = True,
        start_watcher: bool = False,
    ) -> None:
        """Initialize the RAG client.

        Args:
            docs_folder: Folder containing documents to index.
            chroma_path: Path to ChromaDB persistence directory.
            openai_base_url: Base URL for OpenAI-compatible API.
            embedding_model: Model to use for embeddings.
            embedding_api_key: API key for embedding model.
            chat_api_key: API key for chat completions.
            default_top_k: Default number of chunks to retrieve.
            enable_rag_tools: Allow agent to fetch full documents.
            start_watcher: Whether to start file watcher immediately.

        """
        self.docs_folder = docs_folder.resolve()
        self.chroma_path = chroma_path.resolve()
        self.openai_base_url = openai_base_url.rstrip("/")
        self.chat_api_key = chat_api_key
        self.default_top_k = default_top_k
        self.enable_rag_tools = enable_rag_tools

        # Ensure docs folder exists
        self.docs_folder.mkdir(exist_ok=True, parents=True)

        # Initialize ChromaDB collection
        logger.info("Initializing RAG collection...")
        self.collection: Collection = init_collection(
            self.chroma_path,
            name="docs",
            embedding_model=embedding_model,
            openai_base_url=self.openai_base_url,
            openai_api_key=embedding_api_key,
        )

        # Load existing file hashes from metadata
        logger.info("Loading existing file index...")
        self.file_hashes: dict[str, str] = load_hashes_from_metadata(self.collection)
        logger.info("Loaded %d files from index.", len(self.file_hashes))

        # Load reranker model
        logger.info("Loading reranker model...")
        self.reranker_model: OnnxCrossEncoder = get_reranker_model()

        # Background watcher task
        self._watch_task: asyncio.Task | None = None
        self._index_thread: threading.Thread | None = None

        if start_watcher:
            self.start()

    def start(self) -> None:
        """Start background file watcher and initial indexing."""
        # Start file watcher
        if self._watch_task is None:
            self._watch_task = asyncio.create_task(
                watch_docs(self.collection, self.docs_folder, self.file_hashes),
            )

        # Start initial indexing in background thread
        if self._index_thread is None or not self._index_thread.is_alive():
            self._index_thread = threading.Thread(
                target=initial_index,
                args=(self.collection, self.docs_folder, self.file_hashes),
                daemon=True,
            )
            self._index_thread.start()

    async def stop(self) -> None:
        """Stop the background file watcher."""
        if self._watch_task:
            self._watch_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._watch_task
            self._watch_task = None

    async def process_request(
        self,
        request: ChatRequest,
        api_key: str | None = None,
    ) -> Any:
        """Process a ChatRequest with RAG context.

        This method accepts a ChatRequest directly, preserving any extra fields.
        Use this for HTTP API endpoints that need to pass through extra fields.

        Args:
            request: The chat request to process.
            api_key: API key (overrides default).

        Returns:
            OpenAI-compatible response dict or StreamingResponse.

        """
        return await process_chat_request(
            request,
            self.collection,
            self.reranker_model,
            self.openai_base_url,
            self.docs_folder,
            default_top_k=self.default_top_k,
            api_key=api_key or self.chat_api_key,
            enable_rag_tools=self.enable_rag_tools,
        )

    def list_files(self) -> list[dict[str, Any]]:
        """List all indexed files.

        Returns:
            List of file info dicts with name, path, type, chunks, indexed_at.

        """
        metadatas = get_all_metadata(self.collection)

        files: dict[str, dict[str, Any]] = {}
        for meta in metadatas:
            if not meta:
                continue
            fp = meta["file_path"]
            if fp not in files:
                files[fp] = {
                    "name": meta["source"],
                    "path": fp,
                    "type": meta["file_type"],
                    "chunks": 0,
                    "indexed_at": meta["indexed_at"],
                }
            files[fp]["chunks"] += 1

        return list(files.values())

    def reindex(self, blocking: bool = False) -> None:
        """Trigger reindexing of all documents.

        Args:
            blocking: If True, wait for indexing to complete.

        """
        logger.info("Reindex requested.")
        if blocking:
            initial_index(self.collection, self.docs_folder, self.file_hashes)
        else:
            thread = threading.Thread(
                target=initial_index,
                args=(self.collection, self.docs_folder, self.file_hashes),
                daemon=True,
            )
            thread.start()
