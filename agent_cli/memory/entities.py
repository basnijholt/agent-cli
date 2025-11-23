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
