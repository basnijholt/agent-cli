"""Tests for core Chroma helpers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from agent_cli.core import chroma


class _Meta(BaseModel):
    source: str
    tags: list[str]
    score: float | None = None


class _FakeCollection:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], list[str], list[dict[str, Any]]]] = []

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> None:
        self.calls.append((ids, documents, metadatas))


def test_flatten_and_upsert_uses_base_models() -> None:
    """Ensure metadata serialization accepts BaseModel and preserves lists."""
    m = _Meta(source="doc", tags=["a", "b"])
    collection = _FakeCollection()

    chroma.upsert(collection, ids=["1"], documents=["text"], metadatas=[m])

    assert collection.calls
    ids, docs, metas = collection.calls[0]
    assert ids == ["1"]
    assert docs == ["text"]
    assert metas == [{"source": "doc", "tags": ["a", "b"]}]
