"""ChromaDB helpers for memory storage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_cli.constants import DEFAULT_OPENAI_EMBEDDING_MODEL
from agent_cli.core.chroma import delete as delete_docs
from agent_cli.core.chroma import init_collection, upsert
from agent_cli.memory._filters import to_chroma_where
from agent_cli.memory.models import MemoryMetadata, StoredMemory

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from chromadb import Collection


def init_memory_collection(
    persistence_path: Path,
    *,
    collection_name: str = "memory",
    embedding_model: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
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
    filters: dict[str, Any] | None = None,
) -> list[StoredMemory]:
    """Query for relevant memory entries and return structured results."""
    base_filters: list[dict[str, Any]] = [
        {"conversation_id": conversation_id},
        {"role": {"$ne": "summary"}},
    ]
    if filters:
        chroma_filters = to_chroma_where(filters)
        if chroma_filters:
            base_filters.append(chroma_filters)
    raw = collection.query(
        query_texts=[text],
        n_results=n_results,
        where={"$and": base_filters},
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
        assert doc_id is not None
        records.append(
            StoredMemory(
                id=doc_id,
                content=doc,
                metadata=MemoryMetadata(**dict(meta)),
                distance=float(dist) if dist is not None else None,
                embedding=[float(x) for x in emb] if emb is not None else None,
            ),
        )
    return records


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

    records: list[StoredMemory] = []
    for doc, meta, entry_id in zip(docs, metas, ids, strict=False):
        records.append(
            StoredMemory(
                id=entry_id,
                content=doc,
                metadata=MemoryMetadata(**dict(meta)),
                distance=None,
            ),
        )
    return records


def delete_entries(collection: Collection, ids: list[str]) -> None:
    """Delete entries by ID."""
    delete_docs(collection, ids)


def upsert_summary_entries(
    collection: Collection,
    entries: list[dict[str, Any]],
) -> list[str]:
    """Store pre-built summary entries to ChromaDB.

    This is the low-level helper that accepts entries already built by
    SummaryResult.to_storage_metadata(). Use this when you already have
    the entries (e.g., after writing files) to avoid duplicate serialization.

    Args:
        collection: ChromaDB collection.
        entries: List of entry dicts with 'id', 'content', and 'metadata' keys.

    Returns:
        List of IDs that were upserted.

    """
    if not entries:
        return []

    ids: list[str] = []
    contents: list[str] = []
    metadatas: list[MemoryMetadata] = []

    for entry in entries:
        ids.append(entry["id"])
        contents.append(entry["content"])
        # Convert the raw metadata dict to MemoryMetadata
        meta_dict = entry["metadata"]
        metadatas.append(MemoryMetadata(**meta_dict))

    upsert_memories(collection, ids=ids, contents=contents, metadatas=metadatas)
    return ids


def upsert_hierarchical_summary(
    collection: Collection,
    conversation_id: str,
    summary_result: Any,
) -> list[str]:
    """Store all levels of a hierarchical summary.

    Convenience wrapper that calls to_storage_metadata() and then
    upsert_summary_entries(). If you already have the entries built,
    call upsert_summary_entries() directly to avoid duplicate work.

    Args:
        collection: ChromaDB collection.
        conversation_id: The conversation this summary belongs to.
        summary_result: A SummaryResult from the adaptive summarizer.

    Returns:
        List of IDs that were upserted.

    """
    entries = summary_result.to_storage_metadata(conversation_id)
    return upsert_summary_entries(collection, entries)


def get_summary_at_level(
    collection: Collection,
    conversation_id: str,
    level: int,
) -> list[StoredMemory]:
    """Retrieve summaries at a specific level for a conversation.

    Args:
        collection: ChromaDB collection.
        conversation_id: The conversation to retrieve summaries for.
        level: Summary level (1=chunk, 2=group, 3=final).

    Returns:
        List of StoredMemory entries at the requested level.

    """
    filters: list[dict[str, Any]] = [
        {"conversation_id": conversation_id},
        {"role": "summary"},
        {"level": level},
    ]
    result = collection.get(where={"$and": filters})
    docs = result.get("documents") or []
    metas = result.get("metadatas") or []
    ids = result.get("ids") or []

    records: list[StoredMemory] = []
    for doc, meta, entry_id in zip(docs, metas, ids, strict=False):
        records.append(
            StoredMemory(
                id=entry_id,
                content=doc,
                metadata=MemoryMetadata(**dict(meta)),
                distance=None,
            ),
        )
    return records


def get_final_summary(
    collection: Collection,
    conversation_id: str,
) -> StoredMemory | None:
    """Get the L3 (final) summary for a conversation.

    This is a convenience wrapper around get_summary_at_level for the
    most common use case of retrieving the top-level summary.

    Args:
        collection: ChromaDB collection.
        conversation_id: The conversation to retrieve the summary for.

    Returns:
        The final summary entry, or None if not found.

    """
    summaries = get_summary_at_level(collection, conversation_id, level=3)
    # Return the one marked as final, or the first if none marked
    for summary in summaries:
        if summary.metadata.is_final:
            return summary
    return summaries[0] if summaries else None


def delete_summaries(
    collection: Collection,
    conversation_id: str,
    *,
    levels: list[int] | None = None,
) -> int:
    """Delete summary entries for a conversation.

    Args:
        collection: ChromaDB collection.
        conversation_id: The conversation to delete summaries from.
        levels: Optional list of levels to delete. If None, deletes all levels.

    Returns:
        Number of entries deleted.

    """
    filters: list[dict[str, Any]] = [
        {"conversation_id": conversation_id},
        {"role": "summary"},
    ]
    if levels:
        filters.append({"level": {"$in": levels}})

    # First get the IDs to count them
    result = collection.get(where={"$and": filters})
    ids = result.get("ids") or []

    if ids:
        delete_docs(collection, list(ids))

    return len(ids)
