"""Shared ChromaDB helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_cli.constants import DEFAULT_OPENAI_EMBEDDING_MODEL

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from chromadb import Collection
    from pydantic import BaseModel


def init_collection(
    persistence_path: Path,
    *,
    name: str,
    embedding_model: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
    openai_base_url: str | None = None,
    openai_api_key: str | None = None,
    subdir: str | None = None,
) -> Collection:
    """Initialize a Chroma collection with OpenAI-compatible embeddings."""
    import chromadb  # noqa: PLC0415
    from chromadb.config import Settings  # noqa: PLC0415
    from chromadb.utils import embedding_functions  # noqa: PLC0415

    target_path = persistence_path / subdir if subdir else persistence_path
    target_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(target_path),
        settings=Settings(anonymized_telemetry=False),
    )
    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_base=openai_base_url,
        api_key=openai_api_key or "dummy",
        model_name=embedding_model,
    )
    return client.get_or_create_collection(name=name, embedding_function=embed_fn)


def flatten_metadatas(metadatas: Sequence[BaseModel]) -> list[dict[str, Any]]:
    """Serialize metadata models to JSON-safe dicts while preserving lists."""
    return [meta.model_dump(mode="json", exclude_none=True) for meta in metadatas]


def upsert(
    collection: Collection,
    *,
    ids: list[str],
    documents: list[str],
    metadatas: Sequence[BaseModel],
    batch_size: int = 10,
) -> None:
    """Upsert documents with JSON-serialized metadata.

    Args:
        collection: ChromaDB collection.
        ids: Document IDs.
        documents: Document contents.
        metadatas: Pydantic metadata models.
        batch_size: Max documents per embedding API call (default: 10).

    """
    if not ids:
        return
    serialized = flatten_metadatas(metadatas)

    # Process in batches to avoid overwhelming the embedding service
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i : i + batch_size]
        batch_docs = documents[i : i + batch_size]
        batch_metas = serialized[i : i + batch_size]
        collection.upsert(ids=batch_ids, documents=batch_docs, metadatas=batch_metas)


def delete(collection: Collection, ids: list[str]) -> None:
    """Delete documents by ID."""
    if ids:
        collection.delete(ids=ids)


def delete_where(collection: Collection, where: Mapping[str, Any]) -> None:
    """Delete documents by a filter."""
    collection.delete(where=where)
