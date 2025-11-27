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
from agent_cli.summarizer.adaptive import (
    THRESHOLD_BRIEF,
    THRESHOLD_NONE,
    determine_level,
    summarize,
)
from agent_cli.summarizer.models import SummaryLevel, SummaryResult


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


class TestDetermineLevel:
    """Tests for level determination based on token count.

    The simplified approach has 3 levels:
    - NONE: Very short content (< 100 tokens)
    - BRIEF: Short content (100-500 tokens)
    - MAP_REDUCE: Everything else (uses map-reduce)
    """

    def test_none_level_threshold(self) -> None:
        """Test NONE level for very short content."""
        assert determine_level(50) == SummaryLevel.NONE
        assert determine_level(99) == SummaryLevel.NONE

    def test_brief_level_threshold(self) -> None:
        """Test BRIEF level for short content."""
        assert determine_level(100) == SummaryLevel.BRIEF
        assert determine_level(300) == SummaryLevel.BRIEF
        assert determine_level(499) == SummaryLevel.BRIEF

    def test_map_reduce_level_for_longer_content(self) -> None:
        """Test that content >= 500 tokens uses MAP_REDUCE."""
        assert determine_level(500) == SummaryLevel.MAP_REDUCE
        assert determine_level(1500) == SummaryLevel.MAP_REDUCE
        assert determine_level(5000) == SummaryLevel.MAP_REDUCE
        assert determine_level(20000) == SummaryLevel.MAP_REDUCE

    def test_thresholds_match_constants(self) -> None:
        """Verify thresholds match the module constants."""
        assert THRESHOLD_NONE == 100
        assert THRESHOLD_BRIEF == 500


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
    async def test_empty_content_returns_none_level(
        self,
        config: SummarizerConfig,
    ) -> None:
        """Test that empty content returns NONE level result."""
        result = await summarize("", config)
        assert result.level == SummaryLevel.NONE
        assert result.summary is None
        assert result.input_tokens == 0
        assert result.output_tokens == 0

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_none_level(
        self,
        config: SummarizerConfig,
    ) -> None:
        """Test that whitespace-only content returns NONE level result."""
        result = await summarize("   \n\n   ", config)
        assert result.level == SummaryLevel.NONE
        assert result.summary is None

    @pytest.mark.asyncio
    async def test_very_short_content_no_summary(
        self,
        config: SummarizerConfig,
    ) -> None:
        """Test that very short content gets NONE level (no summary)."""
        # Less than 100 tokens
        result = await summarize("Hello world", config)
        assert result.level == SummaryLevel.NONE
        assert result.summary is None

    @pytest.mark.asyncio
    @patch("agent_cli.summarizer.adaptive._brief_summary")
    async def test_brief_level_calls_brief_summary(
        self,
        mock_brief: AsyncMock,
        config: SummarizerConfig,
    ) -> None:
        """Test that BRIEF level content calls _brief_summary."""
        mock_brief.return_value = "Brief summary."

        # Create content that's ~100-500 tokens
        content = "This is a test sentence. " * 30  # ~150 tokens

        result = await summarize(content, config)

        mock_brief.assert_called_once_with(content, config)
        assert result.level == SummaryLevel.BRIEF
        assert result.summary == "Brief summary."

    @pytest.mark.asyncio
    @patch("agent_cli.summarizer.adaptive._map_reduce_summary")
    async def test_longer_content_uses_map_reduce(
        self,
        mock_map_reduce: AsyncMock,
        config: SummarizerConfig,
    ) -> None:
        """Test that content >= 500 tokens uses map-reduce."""
        mock_result = SummaryResult(
            level=SummaryLevel.MAP_REDUCE,
            summary="Map-reduce summary.",
            input_tokens=800,
            output_tokens=100,
            compression_ratio=0.125,
        )
        mock_map_reduce.return_value = mock_result

        # Create content that's ~500+ tokens
        content = "This is a test sentence with more words. " * 100  # ~800 tokens

        result = await summarize(content, config, content_type="general")

        mock_map_reduce.assert_called_once()
        assert result.summary == "Map-reduce summary."

    @pytest.mark.asyncio
    @patch("agent_cli.summarizer.adaptive._map_reduce_summary")
    async def test_prior_summary_passed_to_map_reduce(
        self,
        mock_map_reduce: AsyncMock,
        config: SummarizerConfig,
    ) -> None:
        """Test that prior_summary is passed to _map_reduce_summary."""
        mock_result = SummaryResult(
            level=SummaryLevel.MAP_REDUCE,
            summary="Updated summary.",
            input_tokens=800,
            output_tokens=100,
            compression_ratio=0.125,
        )
        mock_map_reduce.return_value = mock_result

        content = "This is a test sentence with more words. " * 100
        prior = "Previous context summary."

        await summarize(content, config, prior_summary=prior)

        # Verify prior_summary was passed
        call_args = mock_map_reduce.call_args
        assert call_args[0][3] == prior  # prior_summary is 4th positional arg

    @pytest.mark.asyncio
    @patch("agent_cli.summarizer.adaptive._map_reduce_summary")
    async def test_very_long_content_uses_map_reduce(
        self,
        mock_map_reduce: AsyncMock,
        config: SummarizerConfig,
    ) -> None:
        """Test that very long content uses map-reduce."""
        mock_result = SummaryResult(
            level=SummaryLevel.MAP_REDUCE,
            summary="Long content summary.",
            input_tokens=20000,
            output_tokens=500,
            compression_ratio=0.025,
            collapse_depth=2,
        )
        mock_map_reduce.return_value = mock_result

        # Create content that's > 15000 tokens
        content = "Word " * 20000

        result = await summarize(content, config)

        assert mock_map_reduce.called
        assert result.level == SummaryLevel.MAP_REDUCE


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
