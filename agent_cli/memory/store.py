"""ChromaDB helpers for memory storage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_cli.core.chroma import delete as delete_docs
from agent_cli.core.chroma import init_collection, upsert
from agent_cli.memory.models import MemoryMetadata, StoredMemory

if TYPE_CHECKING:
    from collections.abc import Sequence
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
    return init_collection(
        persistence_path,
        name=collection_name,
        embedding_model=embedding_model,
        openai_base_url=openai_base_url,
        openai_api_key=openai_api_key,
        subdir="chroma",
    )


def upsert_memories(
    collection: Collection,
    ids: list[str],
    contents: list[str],
    metadatas: Sequence[MemoryMetadata],
) -> None:
    """Persist memory entries."""
    upsert(collection, ids=ids, documents=contents, metadatas=metadatas)


def query_memories(
    collection: Collection,
    *,
    conversation_id: str,
    text: str,
    n_results: int,
) -> list[StoredMemory]:
    """Query for relevant memory entries and return structured results."""
    filters = [
        {"conversation_id": conversation_id},
        {"role": {"$ne": "summary"}},
    ]
    raw = collection.query(
        query_texts=[text],
        n_results=n_results,
        where={"$and": filters},
        include=["documents", "metadatas", "distances", "embeddings"],
    )
    docs_list = raw.get("documents")
    docs = docs_list[0] if docs_list else []

    metas_list = raw.get("metadatas")
    metas = metas_list[0] if metas_list else []

    ids_list = raw.get("ids")
    ids = ids_list[0] if ids_list else []

    dists_list = raw.get("distances")
    distances = dists_list[0] if dists_list else []

    raw_embeddings = raw.get("embeddings")
    embeddings: list[Any] = []
    if raw_embeddings and len(raw_embeddings) > 0 and raw_embeddings[0] is not None:
        embeddings = raw_embeddings[0]

    if len(embeddings) != len(docs):
        msg = f"Chroma returned embeddings of unexpected length: {len(embeddings)} vs {len(docs)}"
        raise ValueError(msg)
    records: list[StoredMemory] = []
    for doc, meta, doc_id, dist, emb in zip(
        docs,
        metas,
        ids,
        distances,
        embeddings,
        strict=False,
    ):
        if doc_id is None:
            msg = "Chroma returned a memory row without an id"
            raise ValueError(msg)
        records.append(
            StoredMemory(
                id=str(doc_id),
                content=str(doc),
                metadata=MemoryMetadata(**dict(meta)),
                distance=float(dist) if dist is not None else None,
                embedding=[float(x) for x in emb] if emb is not None else None,
            ),
        )
    return records


def get_summary_entry(
    collection: Collection,
    conversation_id: str,
    *,
    role: str = "summary",
) -> StoredMemory | None:
    """Return the latest summary entry for a conversation, if present."""
    result = collection.get(
        where={"$and": [{"conversation_id": conversation_id}, {"role": role}]},
    )
    docs = result.get("documents") or []
    metas = result.get("metadatas") or []
    ids = result.get("ids") or []

    doc_list = docs[0] if docs and isinstance(docs[0], list) else docs
    meta_list = metas[0] if metas and isinstance(metas[0], list) else metas

    if not doc_list or not meta_list or not ids:
        return None

    return StoredMemory(
        id=str(ids[0]),
        content=str(doc_list[0]),
        metadata=MemoryMetadata(**dict(meta_list[0])),
        distance=None,
    )


def list_conversation_entries(
    collection: Collection,
    conversation_id: str,
    *,
    include_summary: bool = False,
) -> list[StoredMemory]:
    """List all entries for a conversation (optionally excluding summary)."""
    filters: list[dict[str, Any]] = [{"conversation_id": conversation_id}]
    if not include_summary:
        filters.append({"role": {"$ne": "summary"}})
    result = collection.get(where={"$and": filters} if len(filters) > 1 else filters[0])
    docs = result.get("documents") or []
    metas = result.get("metadatas") or []
    ids = result.get("ids") or []

    doc_list = docs[0] if docs and isinstance(docs[0], list) else docs
    meta_list = metas[0] if metas and isinstance(metas[0], list) else metas

    records: list[StoredMemory] = []
    for doc, meta, entry_id in zip(doc_list, meta_list, ids, strict=False):
        records.append(
            StoredMemory(
                id=str(entry_id),
                content=str(doc),
                metadata=MemoryMetadata(**dict(meta)),
                distance=None,
            ),
        )
    return records


def delete_entries(collection: Collection, ids: list[str]) -> None:
    """Delete entries by ID."""
    delete_docs(collection, ids)
