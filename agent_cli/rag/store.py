"""ChromaDB functional interface."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import chromadb
from chromadb.utils import embedding_functions

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

logger = logging.getLogger("agent_cli.rag.store")


def init_collection(
    persistence_path: Path,
    embedding_provider: str = "local",
    embedding_model: str = "all-MiniLM-L6-v2",
    openai_base_url: str | None = None,
    openai_api_key: str | None = None,
) -> Collection:
    """Initialize the Vector Database collection."""
    client = chromadb.PersistentClient(path=str(persistence_path))

    if embedding_provider == "openai":
        # Use OpenAI-compatible embedding (works for Ollama/llama.cpp too)
        logger.info(
            "Using OpenAI embedding: model=%s, base_url=%s",
            embedding_model,
            openai_base_url,
        )
        embed_fn = embedding_functions.OpenAIEmbeddingFunction(
            api_base=openai_base_url,
            api_key=openai_api_key or "dummy",  # Local servers usually ignore key but need one
            model_name=embedding_model,
        )
    else:
        # Default local SentenceTransformers
        logger.info("Using local SentenceTransformer embedding: model=%s", embedding_model)
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model,
        )

    return client.get_or_create_collection(name="docs", embedding_function=embed_fn)


def upsert_docs(
    collection: Collection,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    """Upsert documents into the collection."""
    if not ids:
        return
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


def delete_docs(collection: Collection, ids: list[str]) -> None:
    """Delete documents by ID."""
    if not ids:
        return
    collection.delete(ids=ids)


def delete_by_file_path(collection: Collection, file_path: str) -> int:
    """Delete all chunks associated with a file path.

    Returns:
        Number of chunks deleted.

    """
    results = collection.get(where={"file_path": file_path})
    if results and results["ids"]:
        count = len(results["ids"])
        collection.delete(ids=results["ids"])
        return count
    return 0


def query_docs(collection: Collection, text: str, n_results: int) -> dict[str, Any]:
    """Query the collection."""
    return collection.query(query_texts=[text], n_results=n_results)


def get_all_metadata(collection: Collection) -> list[dict[str, Any]]:
    """Retrieve all metadata from the collection."""
    result = collection.get(include=["metadatas"])
    return result.get("metadatas", []) or []  # type: ignore[return-value]


def count_docs(collection: Collection) -> int:
    """Return total number of documents."""
    return collection.count()
