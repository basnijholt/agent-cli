"""ChromaDB helpers for memory storage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import chromadb
from chromadb.utils import embedding_functions

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection


def init_memory_collection(
    persistence_path: Path,
    *,
    collection_name: str = "memory",
    embedding_model: str = "text-embedding-3-small",
    openai_base_url: str | None = None,
    openai_api_key: str | None = None,
) -> Collection:
    """Initialize or create the memory collection."""
    client = chromadb.PersistentClient(path=str(persistence_path))
    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_base=openai_base_url,
        api_key=openai_api_key or "dummy",
        model_name=embedding_model,
    )
    return client.get_or_create_collection(name=collection_name, embedding_function=embed_fn)


def upsert_memories(
    collection: Collection,
    ids: list[str],
    contents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    """Persist memory entries."""
    if not ids:
        return
    collection.upsert(ids=ids, documents=contents, metadatas=metadatas)


def query_memories(
    collection: Collection,
    *,
    conversation_id: str,
    text: str,
    n_results: int,
) -> dict[str, Any]:
    """Query for relevant memory entries."""
    return collection.query(
        query_texts=[text],
        n_results=n_results,
        where={"conversation_id": conversation_id},
    )
