"""Data models for adaptive summarization."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field

# Hierarchical level constants for storage
HIERARCHICAL_LEVEL_L1 = 1
HIERARCHICAL_LEVEL_L2 = 2
HIERARCHICAL_LEVEL_L3 = 3


class SummaryLevel(IntEnum):
    """Summary granularity levels based on input complexity.

    Thresholds are based on Mem0 research showing optimal compression ratios
    at different content lengths. Token counts are approximate guidelines.
    """

    NONE = 0
    """< 100 tokens: No summary needed, facts only."""

    BRIEF = 1
    """100-500 tokens: Single-sentence summary (~20% compression)."""

    STANDARD = 2
    """500-3000 tokens: Paragraph summary (~12% compression)."""

    DETAILED = 3
    """3000-15000 tokens: Chunked summaries + meta-summary (~7% compression)."""

    HIERARCHICAL = 4
    """> 15000 tokens: Tree of summaries with multiple levels."""


class ChunkSummary(BaseModel):
    """Summary of a single chunk within a hierarchical summary."""

    chunk_index: int = Field(..., description="Index of this chunk in the original content")
    content: str = Field(..., description="The summarized content of this chunk")
    token_count: int = Field(..., ge=0, description="Token count of this summary")
    source_tokens: int = Field(..., ge=0, description="Token count of the source chunk")
    parent_group: int | None = Field(
        default=None,
        description="Index of the L2 group this chunk belongs to",
    )


class HierarchicalSummary(BaseModel):
    """A hierarchical summary with multiple levels.

    Structure inspired by Letta's partial eviction pattern:
    - L1: Individual chunk summaries (parallel processing)
    - L2: Group summaries (groups of ~5 L1 summaries)
    - L3: Final synthesis (single top-level summary)
    """

    l1_summaries: list[ChunkSummary] = Field(
        default_factory=list,
        description="Level 1: Individual chunk summaries",
    )
    l2_summaries: list[str] = Field(
        default_factory=list,
        description="Level 2: Group summaries (if > 5 chunks)",
    )
    l3_summary: str = Field(
        ...,
        description="Level 3: Final synthesized summary",
    )
    chunk_size: int = Field(
        default=3000,
        description="Token size used for chunking",
    )
    chunk_overlap: int = Field(
        default=200,
        description="Token overlap between chunks",
    )

    def get_summary_at_level(self, level: int) -> str | list[str]:
        """Get summary content at a specific level.

        Args:
            level: 1 for chunk summaries, 2 for group summaries, 3 for final.

        Returns:
            Summary content at the requested level.

        """
        if level == HIERARCHICAL_LEVEL_L1:
            return [cs.content for cs in self.l1_summaries]
        if level == HIERARCHICAL_LEVEL_L2:
            return self.l2_summaries if self.l2_summaries else [self.l3_summary]
        return self.l3_summary


class SummaryResult(BaseModel):
    """Result of adaptive summarization.

    Contains the summary at the appropriate level for the input complexity,
    along with metadata about the compression achieved.
    """

    level: SummaryLevel = Field(..., description="The summarization level used")
    summary: str | None = Field(
        default=None,
        description="The final summary text (None for NONE level)",
    )
    hierarchical: HierarchicalSummary | None = Field(
        default=None,
        description="Full hierarchical structure (for DETAILED/HIERARCHICAL levels)",
    )
    input_tokens: int = Field(..., ge=0, description="Token count of the input content")
    output_tokens: int = Field(..., ge=0, description="Token count of the summary")
    compression_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Ratio of output to input tokens (lower = more compression)",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when summary was created",
    )

    @property
    def chunk_summaries(self) -> list[str] | None:
        """Get L1 chunk summaries if available."""
        if self.hierarchical:
            return [cs.content for cs in self.hierarchical.l1_summaries]
        return None

    def to_storage_metadata(self, conversation_id: str) -> list[dict[str, Any]]:
        """Convert to metadata entries for ChromaDB storage.

        Returns a list of metadata dicts, one for each summary level stored.
        """
        entries: list[dict[str, Any]] = []
        timestamp = self.created_at.isoformat()

        if self.level == SummaryLevel.NONE:
            return entries

        # For hierarchical summaries, store each level
        if self.hierarchical:
            # L1: Individual chunk summaries
            entries.extend(
                {
                    "id": f"{conversation_id}:summary:L1:{cs.chunk_index}",
                    "content": cs.content,
                    "metadata": {
                        "conversation_id": conversation_id,
                        "role": "summary",
                        "level": HIERARCHICAL_LEVEL_L1,
                        "chunk_index": cs.chunk_index,
                        "parent_group": cs.parent_group,
                        "token_count": cs.token_count,
                        "created_at": timestamp,
                    },
                }
                for cs in self.hierarchical.l1_summaries
            )

            # L2: Group summaries
            entries.extend(
                {
                    "id": f"{conversation_id}:summary:L2:{idx}",
                    "content": l2_summary,
                    "metadata": {
                        "conversation_id": conversation_id,
                        "role": "summary",
                        "level": HIERARCHICAL_LEVEL_L2,
                        "group_index": idx,
                        "created_at": timestamp,
                    },
                }
                for idx, l2_summary in enumerate(self.hierarchical.l2_summaries)
            )

            # L3: Final summary
            entries.append(
                {
                    "id": f"{conversation_id}:summary:L3:final",
                    "content": self.hierarchical.l3_summary,
                    "metadata": {
                        "conversation_id": conversation_id,
                        "role": "summary",
                        "level": HIERARCHICAL_LEVEL_L3,
                        "is_final": True,
                        "input_tokens": self.input_tokens,
                        "output_tokens": self.output_tokens,
                        "compression_ratio": self.compression_ratio,
                        "created_at": timestamp,
                    },
                },
            )
        elif self.summary:
            # Non-hierarchical: just store the single summary
            entries.append(
                {
                    "id": f"{conversation_id}:summary:L3:final",
                    "content": self.summary,
                    "metadata": {
                        "conversation_id": conversation_id,
                        "role": "summary",
                        "level": HIERARCHICAL_LEVEL_L3,
                        "is_final": True,
                        "summary_level": self.level.name,
                        "input_tokens": self.input_tokens,
                        "output_tokens": self.output_tokens,
                        "compression_ratio": self.compression_ratio,
                        "created_at": timestamp,
                    },
                },
            )

        return entries
