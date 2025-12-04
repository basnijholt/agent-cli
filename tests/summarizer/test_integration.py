"""Integration tests for summarizer with storage layer."""

from __future__ import annotations

from agent_cli.summarizer.models import SummaryResult


class TestSummaryResultStorage:
    """Tests for SummaryResult storage metadata generation."""

    def test_to_storage_metadata_creates_entry(self) -> None:
        """Test that to_storage_metadata creates a valid entry."""
        result = SummaryResult(
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
        assert entry["metadata"]["collapse_depth"] == 1

    def test_no_summary_returns_empty(self) -> None:
        """Test that no summary produces no storage entries."""
        result = SummaryResult(
            summary=None,
            input_tokens=50,
            output_tokens=0,
            compression_ratio=0.0,
        )
        entries = result.to_storage_metadata("test-conversation")
        assert entries == []
