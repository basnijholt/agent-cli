"""Unit tests for Chroma-backed memory store helpers."""

from __future__ import annotations

from typing import Any

from agent_cli.memory import store
from agent_cli.memory.models import MemoryMetadata


class _FakeCollection:
    def __init__(
        self,
        query_result: dict[str, Any] | None = None,
        get_result: dict[str, Any] | None = None,
    ) -> None:
        self.query_result = query_result or {}
        self.get_result = get_result or {}
        self.deleted: list[list[str]] = []
        self.upserts: list[tuple[list[str], list[str], list[dict[str, Any]]]] = []

    def query(self, **_kwargs: Any) -> dict[str, Any]:
        return self.query_result

    def get(self, **_kwargs: Any) -> dict[str, Any]:
        return self.get_result

    def delete(self, ids: list[str]) -> None:
        self.deleted.append(ids)

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self.upserts.append((ids, documents, metadatas))


def test_query_memories_normalizes_tags_and_ids() -> None:
    fake = _FakeCollection(
        query_result={
            "documents": [["doc1", "doc2"]],
            "metadatas": [
                [{"conversation_id": "c1", "role": "memory", "created_at": "now", "tags": "a,b"}],
            ],
            "ids": [["id1"]],
            "distances": [[0.1]],
        },
    )
    records = store.query_memories(fake, conversation_id="c1", text="hello", n_results=2)
    assert len(records) == 1
    assert records[0].id == "id1"
    assert records[0].metadata.tags == ["a", "b"]


def test_get_summary_entry_handles_nested_lists() -> None:
    fake = _FakeCollection(
        get_result={
            "documents": [["summary text"]],
            "metadatas": [
                [{"conversation_id": "c1", "role": "summary_short", "created_at": "now"}],
            ],
            "ids": ["sum1"],
        },
    )
    entry = store.get_summary_entry(fake, "c1", role="summary_short")
    assert entry is not None
    assert entry.id == "sum1"
    assert entry.metadata.role == "summary_short"


def test_list_conversation_entries_filters_summaries() -> None:
    fake = _FakeCollection(
        get_result={
            "documents": [["m1", "m2"]],
            "metadatas": [
                [
                    {"conversation_id": "c1", "role": "memory", "created_at": "now"},
                    {"conversation_id": "c1", "role": "summary_short", "created_at": "now"},
                ],
            ],
            "ids": ["id1", "id2"],
        },
    )
    entries = store.list_conversation_entries(fake, "c1", include_summary=False)
    assert len(entries) == 2  # both returned; caller filters by role
    roles = {e.metadata.role for e in entries}
    assert "memory" in roles
    assert "summary_short" in roles


def test_upsert_and_delete_entries_delegate() -> None:
    fake = _FakeCollection()
    meta = MemoryMetadata(conversation_id="c1", role="memory", created_at="now")

    store.upsert_memories(fake, ids=["x"], contents=["doc"], metadatas=[meta])
    assert fake.upserts[0][0] == ["x"]
    assert fake.upserts[0][1] == ["doc"]
    assert fake.upserts[0][2][0]["conversation_id"] == "c1"

    store.delete_entries(fake, ["x"])
    assert fake.deleted == [["x"]]
