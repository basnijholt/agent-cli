"""Unit tests for summarizer prompt templates."""

from __future__ import annotations

from agent_cli.summarizer._prompts import (
    BRIEF_SUMMARY_PROMPT,
    CHUNK_SUMMARY_PROMPT,
    CONVERSATION_SUMMARY_PROMPT,
    DOCUMENT_SUMMARY_PROMPT,
    JOURNAL_SUMMARY_PROMPT,
    META_SUMMARY_PROMPT,
    STANDARD_SUMMARY_PROMPT,
    format_prior_context,
    format_summaries_for_meta,
    get_prompt_for_content_type,
)


class TestPromptTemplates:
    """Tests for prompt template structure."""

    def test_brief_prompt_has_content_placeholder(self) -> None:
        """Test BRIEF prompt contains content placeholder."""
        assert "{content}" in BRIEF_SUMMARY_PROMPT
        # Test it can be formatted
        result = BRIEF_SUMMARY_PROMPT.format(content="Test content")
        assert "Test content" in result

    def test_standard_prompt_has_placeholders(self) -> None:
        """Test STANDARD prompt contains required placeholders."""
        assert "{content}" in STANDARD_SUMMARY_PROMPT
        assert "{prior_context}" in STANDARD_SUMMARY_PROMPT
        assert "{max_words}" in STANDARD_SUMMARY_PROMPT

        result = STANDARD_SUMMARY_PROMPT.format(
            content="Main content",
            prior_context="Previous context",
            max_words=100,
        )
        assert "Main content" in result
        assert "Previous context" in result
        assert "100" in result

    def test_chunk_prompt_has_placeholders(self) -> None:
        """Test CHUNK prompt contains required placeholders."""
        assert "{content}" in CHUNK_SUMMARY_PROMPT
        assert "{chunk_index}" in CHUNK_SUMMARY_PROMPT
        assert "{total_chunks}" in CHUNK_SUMMARY_PROMPT
        assert "{max_words}" in CHUNK_SUMMARY_PROMPT

        result = CHUNK_SUMMARY_PROMPT.format(
            content="Chunk content",
            chunk_index=1,
            total_chunks=5,
            max_words=50,
        )
        assert "Chunk content" in result
        assert "1" in result
        assert "5" in result

    def test_meta_prompt_has_placeholders(self) -> None:
        """Test META prompt contains required placeholders."""
        assert "{summaries}" in META_SUMMARY_PROMPT
        assert "{max_words}" in META_SUMMARY_PROMPT

        result = META_SUMMARY_PROMPT.format(
            summaries="Summary 1\n\nSummary 2",
            max_words=200,
        )
        assert "Summary 1" in result
        assert "200" in result

    def test_conversation_prompt_has_placeholders(self) -> None:
        """Test CONVERSATION prompt contains required placeholders."""
        assert "{content}" in CONVERSATION_SUMMARY_PROMPT
        assert "{max_words}" in CONVERSATION_SUMMARY_PROMPT
        assert "{prior_context}" in CONVERSATION_SUMMARY_PROMPT

    def test_journal_prompt_has_placeholders(self) -> None:
        """Test JOURNAL prompt contains required placeholders."""
        assert "{content}" in JOURNAL_SUMMARY_PROMPT
        assert "{max_words}" in JOURNAL_SUMMARY_PROMPT
        assert "{prior_context}" in JOURNAL_SUMMARY_PROMPT

    def test_document_prompt_has_placeholders(self) -> None:
        """Test DOCUMENT prompt contains required placeholders."""
        assert "{content}" in DOCUMENT_SUMMARY_PROMPT
        assert "{max_words}" in DOCUMENT_SUMMARY_PROMPT
        assert "{prior_context}" in DOCUMENT_SUMMARY_PROMPT


class TestGetPromptForContentType:
    """Tests for get_prompt_for_content_type function."""

    def test_general_returns_standard(self) -> None:
        """Test general content type returns standard prompt."""
        prompt = get_prompt_for_content_type("general")
        assert prompt == STANDARD_SUMMARY_PROMPT

    def test_conversation_returns_conversation(self) -> None:
        """Test conversation content type returns conversation prompt."""
        prompt = get_prompt_for_content_type("conversation")
        assert prompt == CONVERSATION_SUMMARY_PROMPT

    def test_journal_returns_journal(self) -> None:
        """Test journal content type returns journal prompt."""
        prompt = get_prompt_for_content_type("journal")
        assert prompt == JOURNAL_SUMMARY_PROMPT

    def test_document_returns_document(self) -> None:
        """Test document content type returns document prompt."""
        prompt = get_prompt_for_content_type("document")
        assert prompt == DOCUMENT_SUMMARY_PROMPT

    def test_unknown_returns_standard(self) -> None:
        """Test unknown content type falls back to standard."""
        prompt = get_prompt_for_content_type("unknown_type")
        assert prompt == STANDARD_SUMMARY_PROMPT

    def test_empty_returns_standard(self) -> None:
        """Test empty string falls back to standard."""
        prompt = get_prompt_for_content_type("")
        assert prompt == STANDARD_SUMMARY_PROMPT


class TestFormatPriorContext:
    """Tests for format_prior_context function."""

    def test_with_prior_summary(self) -> None:
        """Test formatting with a prior summary."""
        result = format_prior_context("Previous summary text")
        assert "Prior context" in result
        assert "Previous summary text" in result

    def test_without_prior_summary(self) -> None:
        """Test formatting without prior summary returns empty string."""
        result = format_prior_context(None)
        assert result == ""

    def test_empty_string_prior_summary(self) -> None:
        """Test formatting with empty string prior summary."""
        result = format_prior_context("")
        assert result == ""


class TestFormatSummariesForMeta:
    """Tests for format_summaries_for_meta function."""

    def test_single_summary(self) -> None:
        """Test formatting a single summary."""
        result = format_summaries_for_meta(["Summary one"])
        assert "[Section 1]" in result
        assert "Summary one" in result

    def test_multiple_summaries(self) -> None:
        """Test formatting multiple summaries."""
        summaries = ["First summary", "Second summary", "Third summary"]
        result = format_summaries_for_meta(summaries)

        assert "[Section 1]" in result
        assert "[Section 2]" in result
        assert "[Section 3]" in result
        assert "First summary" in result
        assert "Second summary" in result
        assert "Third summary" in result

    def test_empty_list(self) -> None:
        """Test formatting empty list."""
        result = format_summaries_for_meta([])
        assert result == ""

    def test_summaries_separated(self) -> None:
        """Test summaries are separated by double newlines."""
        summaries = ["Sum 1", "Sum 2"]
        result = format_summaries_for_meta(summaries)
        assert "\n\n" in result
