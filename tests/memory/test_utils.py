"""Unit tests for memory utilities that avoid network calls."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from agent_cli.memory._persistence import evict_if_needed
from agent_cli.memory._store import list_conversation_entries

if TYPE_CHECKING:
    from pathlib import Path


class FakeCollection:
    """Minimal Chroma-like collection for unit tests."""

    def __init__(self) -> None:
        """Initialize in-memory store."""
        self.docs: list[dict[str, Any]] = []

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        """Mimic Chroma upsert."""
        for entry_id, doc, meta in zip(ids, documents, metadatas, strict=False):
            self.docs.append({"id": entry_id, "document": doc, "metadata": meta})

    def get(self, where: dict[str, Any], include: list[str] | None = None) -> dict[str, Any]:
        """Mimic filtered get."""
        _ = include

        def matches(entry: dict[str, Any]) -> bool:
            meta = entry["metadata"]

            def match_clause(clause: dict[str, Any]) -> bool:
                for key, value in clause.items():
                    if isinstance(value, dict) and "$ne" in value:
                        if meta.get(key) == value["$ne"]:
                            return False
                    elif meta.get(key) != value:
                        return False
                return True

            # Support simple dict or {"$and": [ ... ]}
            if "$and" in where:
                return all(match_clause(cl) for cl in where["$and"])
            return match_clause(where)

        filtered = [entry for entry in self.docs if matches(entry)]
        return {
            "documents": [e["document"] for e in filtered],
            "metadatas": [e["metadata"] for e in filtered],
            "ids": [e["id"] for e in filtered],
        }

    def delete(self, ids: list[str]) -> None:
        """Mimic delete by IDs."""
        self.docs = [entry for entry in self.docs if entry["id"] not in ids]


def test_evict_if_needed_removes_oldest(tmp_path: Path) -> None:
    collection = FakeCollection()
    base_meta = {"conversation_id": "c1", "role": "memory"}
    collection.upsert(
        ids=["old", "mid", "new"],
        documents=["old doc", "mid doc", "new doc"],
        metadatas=[
            {**base_meta, "created_at": "2024-01-01T00:00:00Z"},
            {**base_meta, "created_at": "2024-06-01T00:00:00Z"},
            {**base_meta, "created_at": "2024-12-01T00:00:00Z"},
        ],
    )

    with patch("agent_cli.memory._ingest.delete_memory_files"):
        evict_if_needed(collection, tmp_path, "c1", max_entries=2)

    remaining = list_conversation_entries(collection, "c1")
    remaining_ids = {e.id for e in remaining}
    assert remaining_ids == {"mid", "new"}
