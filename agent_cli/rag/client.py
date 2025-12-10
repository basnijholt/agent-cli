"""RagClient - Composable RAG abstraction for indexing and search."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agent_cli.constants import (
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_EMBEDDING_MODEL,
)
from agent_cli.core.chroma import init_collection
from agent_cli.core.reranker import get_reranker_model
from agent_cli.rag._retriever import format_context, rerank_and_filter
from agent_cli.rag._utils import chunk_text, load_document_text
from agent_cli.rag.models import RagSource, RetrievalResult

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

    from agent_cli.core.reranker import OnnxCrossEncoder

logger = logging.getLogger("agent_cli.rag.client")


class RagClient:
    """A composable RAG index for adding documents and searching.

    Designed for building personal knowledge systems. Supports:
    - Adding raw text with metadata (for chat ingestion)
    - Adding files (auto-chunked)
    - Search with metadata filtering
    - Delete by ID or metadata filter

    Example:
        index = RagClient(chroma_path=Path("./my_index"))
        index.add("User asked about Python", metadata={"source": "chatgpt"})
        results = index.search("Python", filters={"source": "chatgpt"})

    """

    def __init__(
        self,
        chroma_path: Path,
        embedding_model: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
        openai_base_url: str = DEFAULT_OPENAI_BASE_URL,
        openai_api_key: str | None = None,
        collection_name: str = "rag_index",
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
    ) -> None:
        """Initialize the RAG index.

        Args:
            chroma_path: Path for ChromaDB persistence.
            embedding_model: OpenAI embedding model name.
            openai_base_url: Base URL for embedding API.
            openai_api_key: API key for embeddings.
            collection_name: Name of the ChromaDB collection.
            chunk_size: Maximum chunk size in characters.
            chunk_overlap: Overlap between chunks in characters.

        """
        self.chroma_path = chroma_path
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

        logger.info("Initializing RAG index at %s", chroma_path)
        self.collection: Collection = init_collection(
            chroma_path,
            name=collection_name,
            embedding_model=embedding_model,
            openai_base_url=openai_base_url,
            openai_api_key=openai_api_key,
        )

        logger.info("Loading reranker model...")
        self.reranker: OnnxCrossEncoder = get_reranker_model()

    def add(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
    ) -> str:
        """Add text to the index.

        Text is automatically chunked if it exceeds chunk_size.

        Args:
            text: The text content to add.
            metadata: Optional metadata dict (e.g., {"source": "chatgpt"}).
            doc_id: Optional document ID. Auto-generated if not provided.

        Returns:
            The document ID (useful for deletion).

        """
        doc_id = doc_id or str(uuid.uuid4())
        metadata = metadata or {}

        # Add indexing timestamp
        metadata["indexed_at"] = datetime.now(UTC).isoformat()
        metadata["doc_id"] = doc_id

        # Chunk the text
        chunks = chunk_text(text, self._chunk_size, self._chunk_overlap)

        if not chunks:
            logger.warning("No chunks generated for doc_id=%s", doc_id)
            return doc_id

        # Generate chunk IDs and metadata
        ids = [f"{doc_id}:{i}" for i in range(len(chunks))]
        metadatas = [
            {
                **metadata,
                "chunk_id": i,
                "total_chunks": len(chunks),
            }
            for i in range(len(chunks))
        ]

        # Upsert to collection
        self.collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
        logger.info("Added doc_id=%s with %d chunks", doc_id, len(chunks))

        return doc_id

    def add_file(
        self,
        file_path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a file to the index.

        File is read, chunked, and indexed with file metadata.

        Args:
            file_path: Path to the file to add.
            metadata: Optional additional metadata.

        Returns:
            The document ID.

        Raises:
            ValueError: If file cannot be read.

        """
        text = load_document_text(file_path)
        if text is None:
            msg = f"Could not read file: {file_path}"
            raise ValueError(msg)

        file_metadata = {
            "source": file_path.name,
            "file_path": str(file_path),
            "file_type": file_path.suffix.lstrip("."),
            **(metadata or {}),
        }

        return self.add(text, file_metadata)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
        min_score: float = 0.2,
    ) -> RetrievalResult:
        """Search the index with optional metadata filtering.

        Uses bi-encoder for initial retrieval, then cross-encoder for reranking.

        Args:
            query: The search query.
            top_k: Number of results to return.
            filters: ChromaDB where clause (e.g., {"source": "chatgpt"}).
            min_score: Minimum relevance score threshold. Results below this are filtered out.

        Returns:
            RetrievalResult with context string and sources.

        """
        # Over-fetch for reranking
        n_candidates = top_k * 3

        # Query with optional filter
        results = self.collection.query(
            query_texts=[query],
            n_results=n_candidates,
            where=filters,
            include=["documents", "metadatas", "distances"],
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        if not docs:
            return RetrievalResult(context="", sources=[])

        # Rerank and filter
        ranked = rerank_and_filter(self.reranker, query, docs, metas, top_k, min_score)

        if not ranked:
            return RetrievalResult(context="", sources=[])

        # Build context and sources
        context = format_context(ranked)
        sources = [
            RagSource(
                source=meta.get("source", "unknown"),
                path=meta.get("file_path", meta.get("doc_id", "unknown")),
                chunk_id=meta.get("chunk_id", 0),
                score=float(score),
            )
            for _doc, meta, score in ranked
        ]

        return RetrievalResult(context=context, sources=sources)

    def delete(self, doc_id: str) -> int:
        """Delete all chunks for a document ID.

        Args:
            doc_id: The document ID to delete.

        Returns:
            Number of chunks deleted.

        """
        # Get all chunk IDs for this doc_id
        results = self.collection.get(
            where={"doc_id": doc_id},
            include=[],
        )
        ids = results.get("ids", [])

        if ids:
            self.collection.delete(ids=ids)
            logger.info("Deleted %d chunks for doc_id=%s", len(ids), doc_id)

        return len(ids)

    def delete_by_metadata(self, filters: dict[str, Any]) -> int:
        """Delete all documents matching a metadata filter.

        Args:
            filters: ChromaDB where clause.

        Returns:
            Number of chunks deleted.

        """
        results = self.collection.get(
            where=filters,
            include=[],
        )
        ids = results.get("ids", [])

        if ids:
            self.collection.delete(ids=ids)
            logger.info("Deleted %d chunks matching filters=%s", len(ids), filters)

        return len(ids)

    def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count documents in the index.

        Args:
            filters: Optional ChromaDB where clause.

        Returns:
            Number of chunks (not documents).

        """
        if filters is None:
            return self.collection.count()

        results = self.collection.get(where=filters, include=[])
        return len(results.get("ids", []))

    def list_sources(self) -> list[str]:
        """List unique source values in the index.

        Returns:
            Sorted list of unique source values.

        """
        results = self.collection.get(include=["metadatas"])
        metadatas = results.get("metadatas", []) or []

        sources = {meta.get("source") for meta in metadatas if meta and meta.get("source")}

        return sorted(sources)
