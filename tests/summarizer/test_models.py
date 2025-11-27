"""Unit tests for summarizer models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_cli.summarizer.models import (
    SummaryLevel,
    SummaryResult,
)


class TestSummaryLevel:
    """Tests for SummaryLevel enum."""

    def test_level_values(self) -> None:
        """Test that levels have correct integer values."""
        assert SummaryLevel.NONE == 0
        assert SummaryLevel.BRIEF == 1
        assert SummaryLevel.MAP_REDUCE == 2

    def test_level_ordering(self) -> None:
        """Test that levels can be compared."""
        assert SummaryLevel.NONE < SummaryLevel.BRIEF
        assert SummaryLevel.BRIEF < SummaryLevel.MAP_REDUCE


class TestSummaryResult:
    """Tests for SummaryResult model."""

    def test_none_level_result(self) -> None:
        """Test result for content that needs no summary."""
        result = SummaryResult(
            level=SummaryLevel.NONE,
            summary=None,
            input_tokens=50,
            output_tokens=0,
            compression_ratio=0.0,
        )
        assert result.level == SummaryLevel.NONE
        assert result.summary is None
        assert result.collapse_depth == 0

    def test_brief_level_result(self) -> None:
        """Test result for brief summary."""
        result = SummaryResult(
            level=SummaryLevel.BRIEF,
            summary="A brief one-sentence summary.",
            input_tokens=200,
            output_tokens=10,
            compression_ratio=0.05,
        )
        assert result.level == SummaryLevel.BRIEF
        assert result.summary == "A brief one-sentence summary."
        assert result.collapse_depth == 0

    def test_map_reduce_result(self) -> None:
        """Test result for map-reduce summary."""
        result = SummaryResult(
            level=SummaryLevel.MAP_REDUCE,
            summary="A comprehensive summary.",
            input_tokens=5000,
            output_tokens=100,
            compression_ratio=0.02,
            collapse_depth=2,
        )
        assert result.level == SummaryLevel.MAP_REDUCE
        assert result.summary == "A comprehensive summary."
        assert result.collapse_depth == 2

    def test_to_storage_metadata_none_level(self) -> None:
        """Test that NONE level produces no storage entries."""
        result = SummaryResult(
            level=SummaryLevel.NONE,
            summary=None,
            input_tokens=50,
            output_tokens=0,
            compression_ratio=0.0,
        )
        entries = result.to_storage_metadata("conv-123")
        assert entries == []

    def test_to_storage_metadata_simple_summary(self) -> None:
        """Test storage metadata for a summary."""
        result = SummaryResult(
            level=SummaryLevel.BRIEF,
            summary="A brief summary.",
            input_tokens=200,
            output_tokens=10,
            compression_ratio=0.05,
        )
        entries = result.to_storage_metadata("conv-456")
        assert len(entries) == 1
        entry = entries[0]
        assert entry["id"] == "conv-456:summary"
        assert entry["content"] == "A brief summary."
        assert entry["metadata"]["conversation_id"] == "conv-456"
        assert entry["metadata"]["role"] == "summary"
        assert entry["metadata"]["is_final"] is True
        assert entry["metadata"]["summary_level"] == "BRIEF"

    def test_to_storage_metadata_map_reduce(self) -> None:
        """Test storage metadata for map-reduce summary."""
        result = SummaryResult(
            level=SummaryLevel.MAP_REDUCE,
            summary="Final synthesis of content.",
            input_tokens=20000,
            output_tokens=200,
            compression_ratio=0.01,
            collapse_depth=3,
        )
        entries = result.to_storage_metadata("conv-789")

        # Should have 1 entry (the final summary)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["id"] == "conv-789:summary"
        assert entry["content"] == "Final synthesis of content."
        assert entry["metadata"]["summary_level"] == "MAP_REDUCE"
        assert entry["metadata"]["collapse_depth"] == 3
        assert entry["metadata"]["is_final"] is True

    def test_compression_ratio_bounds(self) -> None:
        """Test compression ratio validation."""
        # Valid ratio
        result = SummaryResult(
            level=SummaryLevel.BRIEF,
            summary="Test",
            input_tokens=100,
            output_tokens=10,
            compression_ratio=0.1,
        )
        assert result.compression_ratio == 0.1

        # Ratio must be between 0 and 1
        with pytest.raises(ValueError, match="less than or equal to 1"):
            SummaryResult(
                level=SummaryLevel.BRIEF,
                summary="Test",
                input_tokens=100,
                output_tokens=10,
                compression_ratio=1.5,
            )

    def test_created_at_default(self) -> None:
        """Test that created_at is automatically set."""
        before = datetime.now(UTC)
        result = SummaryResult(
            level=SummaryLevel.BRIEF,
            summary="Test",
            input_tokens=100,
            output_tokens=10,
            compression_ratio=0.1,
        )
        after = datetime.now(UTC)
        # All datetimes should be UTC-aware
        assert before <= result.created_at <= after
