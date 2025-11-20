"""Shared ChromaDB helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

import chromadb
from chromadb.utils import embedding_functions
from pydantic import BaseModel

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection


def init_collection(
    persistence_path: Path,
    *,
    name: str,
    embedding_model: str = "text-embedding-3-small",
    openai_base_url: str | None = None,
    openai_api_key: str | None = None,
    subdir: str | None = None,
) -> Collection:
    """Initialize a Chroma collection with OpenAI-compatible embeddings."""
    target_path = persistence_path / subdir if subdir else persistence_path
    target_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(target_path))
    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_base=openai_base_url,
        api_key=openai_api_key or "dummy",
        model_name=embedding_model,
    )
    return client.get_or_create_collection(name=name, embedding_function=embed_fn)


def flatten_metadatas(metadatas: Sequence[BaseModel | Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convert metadata objects to Chroma-friendly primitives."""
    flattened: list[dict[str, Any]] = []
    for meta in metadatas:
        raw = meta.model_dump() if isinstance(meta, BaseModel) else dict(meta)
        flat: dict[str, Any] = {}
        for key, value in raw.items():
            if value is None:
                flat[key] = None
            elif isinstance(value, (str, int, float, bool)):
                flat[key] = value
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                flat[key] = ",".join(str(item) for item in value)
            else:
                flat[key] = str(value)
        flattened.append(flat)
    return flattened


def upsert(
    collection: Collection,
    *,
    ids: list[str],
    documents: list[str],
    metadatas: Sequence[BaseModel | Mapping[str, Any]],
) -> None:
    """Upsert documents with flattened metadata."""
    if not ids:
        return
    serialized = flatten_metadatas(metadatas)
    collection.upsert(ids=ids, documents=documents, metadatas=serialized)


def delete(collection: Collection, ids: list[str]) -> None:
    """Delete documents by ID."""
    if ids:
        collection.delete(ids=ids)


def delete_where(collection: Collection, where: Mapping[str, Any]) -> None:
    """Delete documents by a filter."""
    collection.delete(where=where)
