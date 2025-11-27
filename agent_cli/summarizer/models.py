"""Data models for map-reduce summarization."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field


class SummaryLevel(IntEnum):
    """Summary strategy based on input length."""

    NONE = 0
    """< 100 tokens: No summary needed."""

    BRIEF = 1
    """100-500 tokens: Single-sentence summary."""

    MAP_REDUCE = 2
    """> 500 tokens: Map-reduce with dynamic collapse."""


class SummaryResult(BaseModel):
    """Result of summarization.

    Contains the summary and metadata about the compression achieved.
    """

    level: SummaryLevel = Field(..., description="The summarization strategy used")
    summary: str | None = Field(
        default=None,
        description="The final summary text (None for NONE level)",
    )
    input_tokens: int = Field(..., ge=0, description="Token count of the input content")
    output_tokens: int = Field(..., ge=0, description="Token count of the summary")
    compression_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Ratio of output to input tokens (lower = more compression)",
    )
    collapse_depth: int = Field(
        default=0,
        ge=0,
        description="Number of collapse iterations in map-reduce (0 = no collapse needed)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when summary was created",
    )

    def to_storage_metadata(self, conversation_id: str) -> list[dict[str, Any]]:
        """Convert to metadata entry for ChromaDB storage.

        Returns a list with a single metadata dict for the summary.
        """
        if self.level == SummaryLevel.NONE or not self.summary:
            return []

        timestamp = self.created_at.isoformat()

        return [
            {
                "id": f"{conversation_id}:summary",
                "content": self.summary,
                "metadata": {
                    "conversation_id": conversation_id,
                    "role": "summary",
                    "is_final": True,
                    "summary_level": self.level.name,
                    "input_tokens": self.input_tokens,
                    "output_tokens": self.output_tokens,
                    "compression_ratio": self.compression_ratio,
                    "collapse_depth": self.collapse_depth,
                    "created_at": timestamp,
                },
            },
        ]
