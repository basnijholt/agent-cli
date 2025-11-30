"""Domain entities for the memory system.

These models represent the "Truth" of the system with strict validation.
Unlike the storage models (files/DB), these entities do not have optional fields
where they shouldn't.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Literal

from pydantic import BaseModel, Field


class Turn(BaseModel):
    """A single user or assistant message in the conversation."""

    id: str = Field(..., description="Unique UUID for this turn")
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class Fact(BaseModel):
    """An atomic piece of information extracted from a user message."""

    id: str = Field(..., description="Unique UUID for this fact")
    conversation_id: str
    content: str
    source_id: str = Field(..., description="UUID of the Turn this fact was extracted from")
    created_at: datetime
    # Facts are always role="memory" implicitly in the storage layer


class Summary(BaseModel):
    """The rolling summary of a conversation."""

    conversation_id: str
    content: str
    created_at: datetime
    # Summaries are role="summary" implicitly


# --- Long Conversation Mode Entities ---


class Segment(BaseModel):
    """A single turn in a long conversation."""

    id: str = Field(..., description="Unique UUID for this segment")
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime

    # Token accounting
    original_tokens: int = Field(..., description="Token count of original content")
    current_tokens: int = Field(..., description="Token count after compression")

    # Compression state
    state: Literal["raw", "summarized", "reference"] = "raw"

    # For summarized segments
    summary: str | None = Field(None, description="Summarized version of content")

    # For reference-type (deduplicated) segments
    refers_to: str | None = Field(None, description="ID of original segment this references")
    diff: str | None = Field(None, description="Diff from the referenced segment")

    # Content fingerprint for dedup
    content_hash: str = ""


class LongConversation(BaseModel):
    """Full conversation state for long conversation mode."""

    id: str = Field(..., description="Unique conversation ID")
    segments: list[Segment] = Field(default_factory=list)

    # Budget tracking
    target_context_tokens: int = Field(
        150_000,
        description="Target context window size (leave room for response)",
    )
    current_total_tokens: int = Field(0, description="Current total tokens in conversation")

    # Compression thresholds
    compress_threshold: float = Field(
        0.8,
        description="Start compressing at this fraction of target",
    )
    raw_recent_tokens: int = Field(
        40_000,
        description="Always keep this many recent tokens raw",
    )
