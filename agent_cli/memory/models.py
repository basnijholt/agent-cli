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
    memory_recency_weight: float | None = None
    memory_score_threshold: float | None = None


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
    replaced_by: str | None = None
    source_id: str | None = None

    # Hierarchical summary fields (only used when role="summary")
    level: int | None = None
    """Summary level: 1=chunk, 2=group, 3=final."""
    is_final: bool | None = None
    """Whether this is the final L3 summary."""
    chunk_index: int | None = None
    """For L1 summaries: index of the source chunk."""
    parent_group: int | None = None
    """For L1 summaries: which L2 group this chunk belongs to."""
    group_index: int | None = None
    """For L2 summaries: index of this group."""
    input_tokens: int | None = None
    """Number of tokens in the original input (L3 only)."""
    output_tokens: int | None = None
    """Number of tokens in the summary output (L3 only)."""
    compression_ratio: float | None = None
    """Ratio of output to input tokens (L3 only)."""
    summary_level_name: str | None = None
    """Name of the SummaryLevel enum used (e.g., 'STANDARD', 'HIERARCHICAL')."""


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
    embedding: list[float] | None = None


class MemoryRetrieval(BaseModel):
    """Result of a memory retrieval operation."""

    entries: list[MemoryEntry]


class MemoryAdd(BaseModel):
    """Add a new memory fact."""

    event: Literal["ADD"] = "ADD"
    text: str


class MemoryUpdate(BaseModel):
    """Update an existing memory fact."""

    event: Literal["UPDATE"] = "UPDATE"
    id: int
    text: str


class MemoryDelete(BaseModel):
    """Delete an existing memory fact."""

    event: Literal["DELETE"] = "DELETE"
    id: int


class MemoryIgnore(BaseModel):
    """Keep an existing memory as is."""

    event: Literal["NONE"] = "NONE"
    id: int


MemoryDecision = MemoryAdd | MemoryUpdate | MemoryDelete | MemoryIgnore
