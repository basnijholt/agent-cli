"""Shared ChromaDB helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import chromadb
from chromadb.utils import embedding_functions

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
    target_path = persistence_path / subdir if subdir else persistence_path
    target_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(target_path))
    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_base=openai_base_url,
        api_key=openai_api_key or "dummy",
        model_name=embedding_model,
    )
    return client.get_or_create_collection(name=name, embedding_function=embed_fn)


def flatten_metadatas(metadatas: Sequence[BaseModel]) -> list[dict[str, Any]]:
    """Serialize metadata models to JSON-safe dicts, flattening nested models.

    ChromaDB only supports flat key-value pairs (no nested dicts), so we need
    to flatten any nested Pydantic models into the top-level dict.
    """
    result = []
    for meta in metadatas:
        flat: dict[str, Any] = {}
        for key, value in meta.model_dump(mode="json", exclude_none=True).items():
            if isinstance(value, dict):
                # Flatten nested dict into top-level
                flat.update(value)
            else:
                flat[key] = value
        result.append(flat)
    return result


def upsert(
    collection: Collection,
    *,
    ids: list[str],
    documents: list[str],
    metadatas: Sequence[BaseModel],
) -> None:
    """Upsert documents with JSON-serialized metadata."""
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
