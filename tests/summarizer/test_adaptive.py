"""Unit tests for adaptive summarization functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.summarizer._utils import (
    SummarizationError,
    SummarizerConfig,
    SummaryOutput,
    generate_summary,
)
from agent_cli.summarizer.adaptive import summarize
from agent_cli.summarizer.map_reduce import MapReduceResult


class TestSummarizerConfig:
    """Tests for SummarizerConfig initialization."""

    def test_basic_init(self) -> None:
        """Test basic initialization with required parameters."""
        config = SummarizerConfig(
            openai_base_url="http://localhost:8000/v1",
            model="llama3.1:8b",
        )
        assert config.openai_base_url == "http://localhost:8000/v1"
        assert config.model == "llama3.1:8b"
        assert config.api_key == "not-needed"

    def test_init_with_api_key(self) -> None:
        """Test initialization with custom API key."""
        config = SummarizerConfig(
            openai_base_url="http://localhost:8000/v1",
            model="gpt-4",
            api_key="sk-test-key",
        )
        assert config.api_key == "sk-test-key"

    def test_init_with_custom_settings(self) -> None:
        """Test initialization with custom chunk settings."""
        config = SummarizerConfig(
            openai_base_url="http://localhost:8000/v1",
            model="gpt-4",
            chunk_size=5000,
            chunk_overlap=300,
            max_concurrent_chunks=10,
            timeout=120.0,
        )
        assert config.chunk_size == 5000
        assert config.chunk_overlap == 300
        assert config.max_concurrent_chunks == 10
        assert config.timeout == 120.0

    def test_trailing_slash_stripped(self) -> None:
        """Test that trailing slash is stripped from base URL."""
        config = SummarizerConfig(
            openai_base_url="http://localhost:8000/v1/",
            model="gpt-4",
        )
        assert config.openai_base_url == "http://localhost:8000/v1"

    def test_default_chunk_size_is_booookscore(self) -> None:
        """Test that default chunk_size follows BOOOOKSCORE recommendation."""
        config = SummarizerConfig(
            openai_base_url="http://localhost:8000/v1",
            model="gpt-4",
        )
        assert config.chunk_size == 2048  # BOOOOKSCORE's tested default

    def test_default_token_max_is_langchain(self) -> None:
        """Test that default token_max follows LangChain's default."""
        config = SummarizerConfig(
            openai_base_url="http://localhost:8000/v1",
            model="gpt-4",
        )
        assert config.token_max == 3000  # LangChain's default


class TestSummarize:
    """Tests for main summarize function."""

    @pytest.fixture
    def config(self) -> SummarizerConfig:
        """Create a config instance."""
        return SummarizerConfig(
            openai_base_url="http://localhost:8000/v1",
            model="gpt-4",
        )

    @pytest.mark.asyncio
    async def test_empty_content_returns_no_summary(
        self,
        config: SummarizerConfig,
    ) -> None:
        """Test that empty content returns result with no summary."""
        result = await summarize("", config)
        assert result.summary is None
        assert result.input_tokens == 0
        assert result.output_tokens == 0

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_no_summary(
        self,
        config: SummarizerConfig,
    ) -> None:
        """Test that whitespace-only content returns result with no summary."""
        result = await summarize("   \n\n   ", config)
        assert result.summary is None

    @pytest.mark.asyncio
    async def test_short_content_returns_as_is(
        self,
        config: SummarizerConfig,
    ) -> None:
        """Test that short content is returned as-is (no LLM call)."""
        # Less than default token_max (3000)
        result = await summarize("Hello world", config)
        assert result.summary == "Hello world"
        assert result.compression_ratio == 1.0  # No compression

    @pytest.mark.asyncio
    async def test_target_tokens_respected(
        self,
        config: SummarizerConfig,
    ) -> None:
        """Test that content fitting target_tokens is returned as-is."""
        content = "Short content"
        result = await summarize(content, config, target_tokens=1000)
        assert result.summary == content
        assert result.compression_ratio == 1.0

    @pytest.mark.asyncio
    async def test_target_ratio_calculates_target(
        self,
        config: SummarizerConfig,
    ) -> None:
        """Test that target_ratio calculates correct target."""
        # Short content that fits even with 10% target
        content = "Hello"
        result = await summarize(content, config, target_ratio=0.1)
        # Content is so short it fits in 10% target
        assert result.summary == content

    @pytest.mark.asyncio
    @patch("agent_cli.summarizer.adaptive._content_aware_summary")
    async def test_content_exceeding_target_gets_summarized(
        self,
        mock_summary: AsyncMock,
        config: SummarizerConfig,
    ) -> None:
        """Test that content exceeding target gets summarized."""
        mock_summary.return_value = "Summarized content."

        # Create content that's ~500 tokens (exceeds target of 100)
        content = "This is a test sentence. " * 100

        result = await summarize(content, config, target_tokens=100)

        mock_summary.assert_called_once()
        assert result.summary == "Summarized content."

    @pytest.mark.asyncio
    @patch("agent_cli.summarizer.adaptive.map_reduce_summarize")
    async def test_large_content_uses_map_reduce(
        self,
        mock_map_reduce: AsyncMock,
        config: SummarizerConfig,
    ) -> None:
        """Test that content exceeding chunk_size uses map-reduce."""
        mock_map_reduce.return_value = MapReduceResult(
            summary="Map-reduce summary.",
            input_tokens=5000,
            output_tokens=100,
            compression_ratio=0.02,
            collapse_depth=1,
            intermediate_summaries=[["chunk1", "chunk2"]],
        )

        # Create content larger than chunk_size (2048)
        content = "Word " * 3000  # ~3000 tokens

        result = await summarize(content, config, target_tokens=500)

        mock_map_reduce.assert_called_once()
        assert result.summary == "Map-reduce summary."


class TestGenerateSummary:
    """Tests for generate_summary function."""

    @pytest.fixture
    def config(self) -> SummarizerConfig:
        """Create a config instance."""
        return SummarizerConfig(
            openai_base_url="http://localhost:8000/v1",
            model="gpt-4",
        )

    @pytest.mark.asyncio
    async def test_generate_summary_with_pydantic_ai(
        self,
        config: SummarizerConfig,
    ) -> None:
        """Test summary generation using PydanticAI agent."""
        # Mock the entire agent creation and run
        mock_result = MagicMock()
        mock_result.output = SummaryOutput(summary="Generated summary.")

        with patch("pydantic_ai.Agent") as mock_agent_class:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            result = await generate_summary("Test prompt", config, max_tokens=100)

            assert result == "Generated summary."
            mock_agent.run.assert_called_once_with("Test prompt")

    @pytest.mark.asyncio
    async def test_raises_summarization_error_on_failure(
        self,
        config: SummarizerConfig,
    ) -> None:
        """Test that SummarizationError is raised on failure."""
        with patch("pydantic_ai.Agent") as mock_agent_class:
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(side_effect=Exception("API error"))
            mock_agent_class.return_value = mock_agent

            with pytest.raises(SummarizationError, match="Summarization failed"):
                await generate_summary("Test prompt", config, max_tokens=100)


class TestSummaryOutput:
    """Tests for SummaryOutput pydantic model."""

    def test_basic_creation(self) -> None:
        """Test creating a SummaryOutput."""
        output = SummaryOutput(summary="Test summary text")
        assert output.summary == "Test summary text"

    def test_whitespace_preserved(self) -> None:
        """Test that whitespace in summary is preserved."""
        output = SummaryOutput(summary="  Summary with spaces  ")
        assert output.summary == "  Summary with spaces  "
