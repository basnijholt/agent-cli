"""Integration tests for summarizer with storage layer."""

from __future__ import annotations

from agent_cli.summarizer.adaptive import determine_level
from agent_cli.summarizer.models import SummaryLevel, SummaryResult


class TestDetermineLevel:
    """Tests for determine_level function with various content sizes."""

    def test_short_content_is_brief(self) -> None:
        """Test that 100-500 token content uses BRIEF."""
        level = determine_level(200)
        assert level == SummaryLevel.BRIEF

    def test_medium_content_is_map_reduce(self) -> None:
        """Test that 500+ token content uses MAP_REDUCE."""
        level = determine_level(1000)
        assert level == SummaryLevel.MAP_REDUCE

    def test_long_content_is_map_reduce(self) -> None:
        """Test that 3000+ token content uses MAP_REDUCE."""
        level = determine_level(5000)
        assert level == SummaryLevel.MAP_REDUCE

    def test_very_long_content_is_map_reduce(self) -> None:
        """Test that content over 15000 tokens still uses MAP_REDUCE."""
        level = determine_level(20000)
        assert level == SummaryLevel.MAP_REDUCE


class TestSummaryResultStorage:
    """Tests for SummaryResult storage metadata generation."""

    def test_to_storage_metadata_creates_entry(self) -> None:
        """Test that to_storage_metadata creates a valid entry."""
        result = SummaryResult(
            level=SummaryLevel.MAP_REDUCE,
            summary="A comprehensive summary.",
            input_tokens=5000,
            output_tokens=100,
            compression_ratio=0.02,
            collapse_depth=1,
        )
        entries = result.to_storage_metadata("test-conversation")

        assert len(entries) == 1
        entry = entries[0]
        assert entry["id"] == "test-conversation:summary"
        assert entry["content"] == "A comprehensive summary."
        assert entry["metadata"]["conversation_id"] == "test-conversation"
        assert entry["metadata"]["role"] == "summary"
        assert entry["metadata"]["is_final"] is True
        assert entry["metadata"]["summary_level"] == "MAP_REDUCE"
        assert entry["metadata"]["collapse_depth"] == 1

    def test_none_level_returns_empty(self) -> None:
        """Test that NONE level produces no storage entries."""
        result = SummaryResult(
            level=SummaryLevel.NONE,
            summary=None,
            input_tokens=50,
            output_tokens=0,
            compression_ratio=0.0,
        )
        entries = result.to_storage_metadata("test-conversation")
        assert entries == []
