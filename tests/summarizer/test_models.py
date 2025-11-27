"""Unit tests for summarizer models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_cli.summarizer.models import (
    ChunkSummary,
    HierarchicalSummary,
    SummaryLevel,
    SummaryResult,
)


class TestSummaryLevel:
    """Tests for SummaryLevel enum."""

    def test_level_values(self) -> None:
        """Test that levels have correct integer values."""
        assert SummaryLevel.NONE == 0
        assert SummaryLevel.BRIEF == 1
        assert SummaryLevel.STANDARD == 2
        assert SummaryLevel.DETAILED == 3
        assert SummaryLevel.HIERARCHICAL == 4

    def test_level_ordering(self) -> None:
        """Test that levels can be compared."""
        assert SummaryLevel.NONE < SummaryLevel.BRIEF
        assert SummaryLevel.BRIEF < SummaryLevel.STANDARD
        assert SummaryLevel.STANDARD < SummaryLevel.DETAILED
        assert SummaryLevel.DETAILED < SummaryLevel.HIERARCHICAL


class TestChunkSummary:
    """Tests for ChunkSummary model."""

    def test_basic_creation(self) -> None:
        """Test creating a chunk summary."""
        chunk = ChunkSummary(
            chunk_index=0,
            content="This is a summary of chunk 1.",
            token_count=10,
            source_tokens=100,
            parent_group=None,
        )
        assert chunk.chunk_index == 0
        assert chunk.content == "This is a summary of chunk 1."
        assert chunk.token_count == 10
        assert chunk.source_tokens == 100
        assert chunk.parent_group is None

    def test_with_parent_group(self) -> None:
        """Test creating a chunk summary with parent group."""
        chunk = ChunkSummary(
            chunk_index=5,
            content="Summary text",
            token_count=8,
            source_tokens=200,
            parent_group=1,
        )
        assert chunk.parent_group == 1

    def test_validation_negative_tokens(self) -> None:
        """Test that negative token counts fail validation."""
        with pytest.raises(ValueError, match="greater than or equal to 0"):
            ChunkSummary(
                chunk_index=0,
                content="Test",
                token_count=-1,
                source_tokens=100,
            )


class TestHierarchicalSummary:
    """Tests for HierarchicalSummary model."""

    def test_basic_creation(self) -> None:
        """Test creating a hierarchical summary."""
        l1 = [
            ChunkSummary(
                chunk_index=0,
                content="Chunk 1 summary",
                token_count=10,
                source_tokens=100,
            ),
            ChunkSummary(
                chunk_index=1,
                content="Chunk 2 summary",
                token_count=12,
                source_tokens=120,
            ),
        ]
        hs = HierarchicalSummary(
            l1_summaries=l1,
            l2_summaries=["Group summary"],
            l3_summary="Final summary of all content.",
        )
        assert len(hs.l1_summaries) == 2
        assert len(hs.l2_summaries) == 1
        assert hs.l3_summary == "Final summary of all content."

    def test_default_chunk_settings(self) -> None:
        """Test default chunk size and overlap."""
        hs = HierarchicalSummary(
            l1_summaries=[],
            l2_summaries=[],
            l3_summary="Final",
        )
        assert hs.chunk_size == 3000
        assert hs.chunk_overlap == 200

    def test_get_summary_at_level_1(self) -> None:
        """Test getting L1 summaries."""
        l1 = [
            ChunkSummary(chunk_index=0, content="C1", token_count=5, source_tokens=50),
            ChunkSummary(chunk_index=1, content="C2", token_count=5, source_tokens=50),
        ]
        hs = HierarchicalSummary(l1_summaries=l1, l2_summaries=[], l3_summary="Final")
        result = hs.get_summary_at_level(1)
        assert result == ["C1", "C2"]

    def test_get_summary_at_level_2_with_l2(self) -> None:
        """Test getting L2 summaries when available."""
        hs = HierarchicalSummary(
            l1_summaries=[],
            l2_summaries=["Group A", "Group B"],
            l3_summary="Final",
        )
        result = hs.get_summary_at_level(2)
        assert result == ["Group A", "Group B"]

    def test_get_summary_at_level_2_fallback(self) -> None:
        """Test getting L2 falls back to L3 when no L2 summaries."""
        hs = HierarchicalSummary(
            l1_summaries=[],
            l2_summaries=[],
            l3_summary="Final summary",
        )
        result = hs.get_summary_at_level(2)
        assert result == ["Final summary"]

    def test_get_summary_at_level_3(self) -> None:
        """Test getting L3 summary."""
        hs = HierarchicalSummary(
            l1_summaries=[],
            l2_summaries=["Group"],
            l3_summary="The final summary",
        )
        result = hs.get_summary_at_level(3)
        assert result == "The final summary"


class TestSummaryResult:
    """Tests for SummaryResult model."""

    def test_none_level_result(self) -> None:
        """Test result for content that needs no summary."""
        result = SummaryResult(
            level=SummaryLevel.NONE,
            summary=None,
            hierarchical=None,
            input_tokens=50,
            output_tokens=0,
            compression_ratio=0.0,
        )
        assert result.level == SummaryLevel.NONE
        assert result.summary is None
        assert result.chunk_summaries is None

    def test_brief_level_result(self) -> None:
        """Test result for brief summary."""
        result = SummaryResult(
            level=SummaryLevel.BRIEF,
            summary="A brief one-sentence summary.",
            hierarchical=None,
            input_tokens=200,
            output_tokens=10,
            compression_ratio=0.05,
        )
        assert result.level == SummaryLevel.BRIEF
        assert result.summary == "A brief one-sentence summary."
        assert result.chunk_summaries is None

    def test_hierarchical_result_with_chunk_summaries(self) -> None:
        """Test hierarchical result exposes chunk summaries."""
        l1 = [
            ChunkSummary(chunk_index=0, content="Chunk 1", token_count=10, source_tokens=100),
            ChunkSummary(chunk_index=1, content="Chunk 2", token_count=10, source_tokens=100),
        ]
        hierarchical = HierarchicalSummary(
            l1_summaries=l1,
            l2_summaries=[],
            l3_summary="Final",
        )
        result = SummaryResult(
            level=SummaryLevel.DETAILED,
            summary="Final",
            hierarchical=hierarchical,
            input_tokens=5000,
            output_tokens=100,
            compression_ratio=0.02,
        )
        assert result.chunk_summaries == ["Chunk 1", "Chunk 2"]

    def test_to_storage_metadata_none_level(self) -> None:
        """Test that NONE level produces no storage entries."""
        result = SummaryResult(
            level=SummaryLevel.NONE,
            summary=None,
            hierarchical=None,
            input_tokens=50,
            output_tokens=0,
            compression_ratio=0.0,
        )
        entries = result.to_storage_metadata("conv-123")
        assert entries == []

    def test_to_storage_metadata_simple_summary(self) -> None:
        """Test storage metadata for simple (non-hierarchical) summary."""
        result = SummaryResult(
            level=SummaryLevel.STANDARD,
            summary="A standard paragraph summary.",
            hierarchical=None,
            input_tokens=1000,
            output_tokens=50,
            compression_ratio=0.05,
        )
        entries = result.to_storage_metadata("conv-456")
        assert len(entries) == 1
        entry = entries[0]
        assert entry["id"] == "conv-456:summary:L3:final"
        assert entry["content"] == "A standard paragraph summary."
        assert entry["metadata"]["conversation_id"] == "conv-456"
        assert entry["metadata"]["role"] == "summary"
        assert entry["metadata"]["level"] == 3
        assert entry["metadata"]["is_final"] is True
        assert entry["metadata"]["summary_level"] == "STANDARD"

    def test_to_storage_metadata_hierarchical(self) -> None:
        """Test storage metadata for hierarchical summary."""
        l1 = [
            ChunkSummary(
                chunk_index=0,
                content="Chunk 0 text",
                token_count=10,
                source_tokens=100,
                parent_group=0,
            ),
            ChunkSummary(
                chunk_index=1,
                content="Chunk 1 text",
                token_count=12,
                source_tokens=120,
                parent_group=0,
            ),
        ]
        hierarchical = HierarchicalSummary(
            l1_summaries=l1,
            l2_summaries=["Group 0 summary"],
            l3_summary="Final synthesis",
        )
        result = SummaryResult(
            level=SummaryLevel.HIERARCHICAL,
            summary="Final synthesis",
            hierarchical=hierarchical,
            input_tokens=20000,
            output_tokens=200,
            compression_ratio=0.01,
        )
        entries = result.to_storage_metadata("conv-789")

        # Should have 2 L1 + 1 L2 + 1 L3 = 4 entries
        assert len(entries) == 4

        # Check L1 entries
        l1_entries = [e for e in entries if e["metadata"]["level"] == 1]
        assert len(l1_entries) == 2
        assert l1_entries[0]["id"] == "conv-789:summary:L1:0"
        assert l1_entries[0]["metadata"]["chunk_index"] == 0

        # Check L2 entry
        l2_entries = [e for e in entries if e["metadata"]["level"] == 2]
        assert len(l2_entries) == 1
        assert l2_entries[0]["id"] == "conv-789:summary:L2:0"
        assert l2_entries[0]["content"] == "Group 0 summary"

        # Check L3 entry
        l3_entries = [e for e in entries if e["metadata"]["level"] == 3]
        assert len(l3_entries) == 1
        assert l3_entries[0]["id"] == "conv-789:summary:L3:final"
        assert l3_entries[0]["metadata"]["is_final"] is True

    def test_compression_ratio_bounds(self) -> None:
        """Test compression ratio validation."""
        # Valid ratio
        result = SummaryResult(
            level=SummaryLevel.BRIEF,
            summary="Test",
            hierarchical=None,
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
                hierarchical=None,
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
            hierarchical=None,
            input_tokens=100,
            output_tokens=10,
            compression_ratio=0.1,
        )
        after = datetime.now(UTC)
        # Compare without timezone since result.created_at may be naive
        assert before.replace(tzinfo=None) <= result.created_at <= after.replace(tzinfo=None)
