"""ChromaDB helpers for memory storage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import chromadb
from chromadb.utils import embedding_functions

from agent_cli.memory.models import MemoryMetadata, StoredMemory

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
) -> list[StoredMemory]:
    """Query for relevant memory entries and return structured results."""
    raw = collection.query(
        query_texts=[text],
        n_results=n_results,
        where={"conversation_id": conversation_id},
    )
    docs = raw.get("documents", [[]])[0] or []
    metas = raw.get("metadatas", [[]])[0] or []
    ids = raw.get("ids", [[]])[0] or []
    distances = raw.get("distances", [[]])[0] or []
    records: list[StoredMemory] = []
    for doc, meta, doc_id, dist in zip(docs, metas, ids, distances, strict=False):
        records.append(
            StoredMemory(
                id=str(doc_id) if doc_id is not None else None,
                content=str(doc),
                metadata=MemoryMetadata(**meta),
                distance=float(dist) if dist is not None else None,
            ),
        )
    return records


def get_summary_entry(collection: Collection, conversation_id: str) -> StoredMemory | None:
    """Return the latest summary entry for a conversation, if present."""
    result = collection.get(
        where={"conversation_id": conversation_id, "role": "summary"},
        include=["documents", "metadatas", "ids"],
    )
    docs = result.get("documents") or []
    metas = result.get("metadatas") or []
    ids = result.get("ids") or []

    doc_list = docs[0] if docs and isinstance(docs[0], list) else docs
    meta_list = metas[0] if metas and isinstance(metas[0], list) else metas

    if not doc_list or not meta_list:
        return None

    return StoredMemory(
        id=str(ids[0]) if ids else None,
        content=str(doc_list[0]),
        metadata=MemoryMetadata(**meta_list[0]),
        distance=None,
    )


def list_conversation_entries(
    collection: Collection,
    conversation_id: str,
    *,
    include_summary: bool = False,
) -> list[StoredMemory]:
    """List all entries for a conversation (optionally excluding summary)."""
    where: dict[str, Any] = {"conversation_id": conversation_id}
    if not include_summary:
        where["role"] = {"$ne": "summary"}
    result = collection.get(where=where, include=["documents", "metadatas", "ids"])
    docs = result.get("documents") or []
    metas = result.get("metadatas") or []
    ids = result.get("ids") or []

    doc_list = docs[0] if docs and isinstance(docs[0], list) else docs
    meta_list = metas[0] if metas and isinstance(metas[0], list) else metas

    records: list[StoredMemory] = []
    for doc, meta, entry_id in zip(doc_list, meta_list, ids, strict=False):
        records.append(
            StoredMemory(
                id=str(entry_id) if entry_id is not None else None,
                content=str(doc),
                metadata=MemoryMetadata(**meta),
                distance=None,
            ),
        )
    return records


def delete_entries(collection: Collection, ids: list[str]) -> None:
    """Delete entries by ID."""
    if ids:
        collection.delete(ids=ids)
