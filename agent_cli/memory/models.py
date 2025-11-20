"""Memory data models."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, field_validator


class Message(BaseModel):
    """Chat message model."""

    role: str
    content: str


class ChatRequest(BaseModel):
    """Chat completion request model with long-term memory support."""

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[Message]
    temperature: float | None = 0.7
    max_tokens: int | None = 1000
    stream: bool | None = False
    memory_id: str | None = None
    memory_top_k: int | None = None


class MemoryEntry(BaseModel):
    """Stored memory entry."""

    role: str
    content: str
    created_at: str
    score: float | None = None


class MemoryMetadata(BaseModel):
    """Metadata for a stored memory document."""

    conversation_id: str
    role: str
    created_at: str
    salience: float | None = None
    tags: list[str] | None = None
    summary_kind: str | None = None
    fact_key: str | None = None


class MemoryExtras(BaseModel):
    """Extras supplied when writing new memory entries."""

    salience: float | None = None
    tags: list[str] | None = None
    fact_key: str | None = None


def _canonical_fact_key(*parts: str) -> str:
    """Canonical, stable key used for conflict resolution."""
    cleaned: list[str] = []
    for part in parts:
        slug = re.sub(r"[^a-z0-9_]+", "", part.strip().lower().replace(" ", "_"))
        slug = re.sub(r"_+", "_", slug).strip("_")
        if slug:
            cleaned.append(slug)
    return "__".join(cleaned)


class FactOutput(BaseModel):
    """Structured fact returned by the LLM."""

    subject: str
    predicate: str
    object: str
    fact: str

    @field_validator("subject", "predicate", "object", "fact")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v or not str(v).strip():
            msg = "field must be non-empty"
            raise ValueError(msg)
        return str(v).strip()

    @property
    def fact_key(self) -> str:
        """Deterministic key for consolidation (subject + predicate)."""
        return _canonical_fact_key(self.subject, self.predicate)


class SummaryOutput(BaseModel):
    """Structured summary returned by the LLM."""

    summary: str

    @field_validator("summary")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v or not str(v).strip():
            msg = "field must be non-empty"
            raise ValueError(msg)
        return str(v).strip()


class StoredMemory(BaseModel):
    """Memory document as stored in the vector DB."""

    id: str | None
    content: str
    metadata: MemoryMetadata
    distance: float | None = None


class MemoryRetrieval(BaseModel):
    """Result of a memory retrieval operation."""

    entries: list[MemoryEntry]
