"""Memory data models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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


class MemoryRetrieval(BaseModel):
    """Result of a memory retrieval operation."""

    entries: list[MemoryEntry]
