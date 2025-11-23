"""ChromaDB functional interface."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent_cli.core.chroma import delete_where, upsert

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chromadb import Collection

    from agent_cli.rag.models import DocMetadata

LOGGER = logging.getLogger(__name__)


def upsert_docs(
    collection: Collection,
    ids: list[str],
    documents: list[str],
    metadatas: Sequence[DocMetadata],
) -> None:
    """Upsert documents into the collection."""
    upsert(collection, ids=ids, documents=documents, metadatas=metadatas)


def delete_by_file_path(collection: Collection, file_path: str) -> None:
    """Delete all chunks associated with a file path."""
    delete_where(collection, {"file_path": file_path})


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
