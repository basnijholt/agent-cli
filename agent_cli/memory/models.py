"""Memory data models."""

from __future__ import annotations

from typing import Literal

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
    summary_kind: str | None = None


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

    id: str
    content: str
    metadata: MemoryMetadata
    distance: float | None = None


class MemoryRetrieval(BaseModel):
    """Result of a memory retrieval operation."""

    entries: list[MemoryEntry]


class ConsolidationDecision(BaseModel):
    """LLM-driven resolution for overlapping facts."""

    id: str
    action: Literal["KEEP", "DELETE", "UPDATE"]
    content: str


class MemoryUpdateDecision(BaseModel):
    """LLM decision for memory reconciliation."""

    event: Literal["ADD", "UPDATE", "DELETE", "NONE"]
    text: str | None = None
    id: str | None = None
