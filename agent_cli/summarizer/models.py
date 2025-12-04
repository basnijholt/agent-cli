"""Data models for map-reduce summarization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class SummarizationError(Exception):
    """Raised when summarization fails after all retries."""


@dataclass
class SummarizerConfig:
    """Configuration for summarization operations.

    Example:
        config = SummarizerConfig(
            openai_base_url="http://localhost:8000/v1",
            model="llama3.1:8b",
        )
        result = await summarize(long_document, config)
        print(f"Compression: {result.compression_ratio:.1%}")

    """

    openai_base_url: str
    model: str
    api_key: str | None = None
    chunk_size: int = 2048  # BOOOOKSCORE's tested default
    token_max: int = 3000  # LangChain's default - target size after compression
    chunk_overlap: int = 200
    max_concurrent_chunks: int = 5

    def __post_init__(self) -> None:
        """Normalize the base URL."""
        self.openai_base_url = self.openai_base_url.rstrip("/")
        if self.api_key is None:
            self.api_key = "not-needed"


class SummaryResult(BaseModel):
    """Result of summarization.

    Contains the summary and metadata about the compression achieved.
    """

    summary: str | None = Field(
        default=None,
        description="The summary text (None if content already fit target)",
    )
    input_tokens: int = Field(..., ge=0, description="Token count of the input content")
    output_tokens: int = Field(..., ge=0, description="Token count of the output")
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
        Returns empty list if no summary was generated.
        """
        if not self.summary:
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
                    "input_tokens": self.input_tokens,
                    "output_tokens": self.output_tokens,
                    "compression_ratio": self.compression_ratio,
                    "collapse_depth": self.collapse_depth,
                    "created_at": timestamp,
                },
            },
        ]
