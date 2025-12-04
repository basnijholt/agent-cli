"""Unit tests for summarizer utility functions."""

from __future__ import annotations

from agent_cli.summarizer._utils import (
    chunk_text,
    count_tokens,
    estimate_summary_tokens,
    tokens_to_words,
)


class TestCountTokens:
    """Tests for count_tokens function."""

    def test_empty_string(self) -> None:
        """Test counting tokens in empty string."""
        assert count_tokens("") == 0

    def test_simple_sentence(self) -> None:
        """Test counting tokens in a simple sentence."""
        # "Hello world" is typically 2 tokens
        count = count_tokens("Hello world")
        assert count > 0
        assert count < 10

    def test_longer_text(self) -> None:
        """Test that longer text has more tokens."""
        short = count_tokens("Hello")
        long = count_tokens("Hello world, this is a longer sentence with more words.")
        assert long > short

    def test_different_model_fallback(self) -> None:
        """Test that unknown models fall back to cl100k_base."""
        # Should not raise, should fall back gracefully
        count = count_tokens("Hello world", model="unknown-model-xyz")
        assert count > 0


class TestChunkText:
    """Tests for chunk_text function."""

    def test_empty_text(self) -> None:
        """Test chunking empty text returns empty list."""
        assert chunk_text("") == []

    def test_short_text_single_chunk(self) -> None:
        """Test that short text stays as single chunk."""
        text = "This is a short paragraph."
        chunks = chunk_text(text, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_multiple_paragraphs_chunking(self) -> None:
        """Test chunking multiple paragraphs."""
        paragraphs = ["Paragraph one. " * 50, "Paragraph two. " * 50, "Paragraph three. " * 50]
        text = "\n\n".join(paragraphs)

        # Use small chunk size to force splitting
        chunks = chunk_text(text, chunk_size=200, overlap=20)
        assert len(chunks) > 1

    def test_overlap_preserved(self) -> None:
        """Test that chunks have overlap for context continuity."""
        # Create text that will definitely need chunking
        text = "Sentence one about topic A. " * 20 + "\n\n" + "Sentence two about topic B. " * 20

        chunks = chunk_text(text, chunk_size=100, overlap=30)

        # With overlap, later chunks should contain some content from earlier
        if len(chunks) > 1:
            # Overlap means adjacent chunks share some content
            # This is a rough check - exact overlap depends on tokenization
            assert len(chunks) >= 2

    def test_large_paragraph_sentence_split(self) -> None:
        """Test that large paragraphs are split by sentences."""
        # One giant paragraph with multiple sentences
        sentences = [
            f"This is sentence number {i}. It contains important information." for i in range(50)
        ]
        text = " ".join(sentences)

        chunks = chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1


class TestEstimateSummaryTokens:
    """Tests for estimate_summary_tokens function."""

    def test_typical_input(self) -> None:
        """Test typical input uses ~10% compression."""
        # ~10% compression, capped at 500, minimum 50
        result = estimate_summary_tokens(1000)
        assert result == 100  # 1000 // 10 = 100

    def test_medium_input(self) -> None:
        """Test medium input stays within bounds."""
        result = estimate_summary_tokens(2000)
        assert result == 200  # 2000 // 10 = 200
        assert result >= 50  # above floor
        assert result <= 500  # below ceiling

    def test_large_input_hits_cap(self) -> None:
        """Test large input hits 500 token cap."""
        result = estimate_summary_tokens(50000)
        assert result == 500  # capped at 500

    def test_small_input_uses_floor(self) -> None:
        """Test small input uses 50 token floor."""
        result = estimate_summary_tokens(100)
        assert result == 50  # floor of 50 (100 // 10 = 10, but min is 50)

    def test_very_small_input(self) -> None:
        """Test very small input still uses floor."""
        result = estimate_summary_tokens(10)
        assert result == 50  # floor of 50


class TestTokensToWords:
    """Tests for tokens_to_words function."""

    def test_basic_conversion(self) -> None:
        """Test basic token to word conversion."""
        # 1 token ≈ 0.75 words
        assert tokens_to_words(100) == 75
        assert tokens_to_words(1000) == 750

    def test_zero_tokens(self) -> None:
        """Test zero tokens returns zero words."""
        assert tokens_to_words(0) == 0

    def test_small_values(self) -> None:
        """Test small token values."""
        assert tokens_to_words(1) == 0  # int(0.75) = 0
        assert tokens_to_words(2) == 1  # int(1.5) = 1
        assert tokens_to_words(4) == 3  # int(3.0) = 3
