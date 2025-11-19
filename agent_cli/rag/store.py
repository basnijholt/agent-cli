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


def init_collection(persistence_path: Path) -> Collection:
    """Initialize the Vector Database collection."""
    client = chromadb.PersistentClient(path=str(persistence_path))
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2",
    )
    return client.get_or_create_collection(
        name="docs",
        embedding_function=embed_fn,
    )


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
