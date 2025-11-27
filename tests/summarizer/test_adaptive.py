"""Unit tests for adaptive summarization functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.summarizer.adaptive import (
    LEVEL_THRESHOLDS,
    SummarizationError,
    SummarizerConfig,
    SummaryOutput,
    _generate_summary,
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


class TestDetermineLevel:
    """Tests for level determination based on token count."""

    def test_none_level_threshold(self) -> None:
        """Test NONE level for very short content."""
        assert determine_level(50) == SummaryLevel.NONE
        assert determine_level(99) == SummaryLevel.NONE

    def test_brief_level_threshold(self) -> None:
        """Test BRIEF level for short content."""
        assert determine_level(100) == SummaryLevel.BRIEF
        assert determine_level(300) == SummaryLevel.BRIEF
        assert determine_level(499) == SummaryLevel.BRIEF

    def test_standard_level_threshold(self) -> None:
        """Test STANDARD level for medium content."""
        assert determine_level(500) == SummaryLevel.STANDARD
        assert determine_level(1500) == SummaryLevel.STANDARD
        assert determine_level(2999) == SummaryLevel.STANDARD

    def test_detailed_level_threshold(self) -> None:
        """Test DETAILED level for longer content."""
        assert determine_level(3000) == SummaryLevel.DETAILED
        assert determine_level(8000) == SummaryLevel.DETAILED
        assert determine_level(14999) == SummaryLevel.DETAILED

    def test_hierarchical_level_threshold(self) -> None:
        """Test HIERARCHICAL level for very long content."""
        assert determine_level(15000) == SummaryLevel.HIERARCHICAL
        assert determine_level(50000) == SummaryLevel.HIERARCHICAL
        assert determine_level(100000) == SummaryLevel.HIERARCHICAL

    def test_thresholds_match_constants(self) -> None:
        """Verify thresholds match the module constants."""
        assert LEVEL_THRESHOLDS[SummaryLevel.NONE] == 100
        assert LEVEL_THRESHOLDS[SummaryLevel.BRIEF] == 500
        assert LEVEL_THRESHOLDS[SummaryLevel.STANDARD] == 3000
        assert LEVEL_THRESHOLDS[SummaryLevel.DETAILED] == 15000


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
    @patch("agent_cli.summarizer.adaptive._standard_summary")
    async def test_standard_level_calls_standard_summary(
        self,
        mock_standard: AsyncMock,
        config: SummarizerConfig,
    ) -> None:
        """Test that STANDARD level content calls _standard_summary."""
        mock_standard.return_value = "Standard summary paragraph."

        # Create content that's ~500-3000 tokens
        content = "This is a test sentence with more words. " * 100  # ~800 tokens

        result = await summarize(content, config, content_type="general")

        mock_standard.assert_called_once_with(content, config, None, "general")
        assert result.level == SummaryLevel.STANDARD
        assert result.summary == "Standard summary paragraph."

    @pytest.mark.asyncio
    @patch("agent_cli.summarizer.adaptive._standard_summary")
    async def test_prior_summary_passed_to_standard(
        self,
        mock_standard: AsyncMock,
        config: SummarizerConfig,
    ) -> None:
        """Test that prior_summary is passed to _standard_summary."""
        mock_standard.return_value = "Updated summary."

        content = "This is a test sentence with more words. " * 100
        prior = "Previous context summary."

        await summarize(content, config, prior_summary=prior)

        mock_standard.assert_called_once_with(content, config, prior, "general")

    @pytest.mark.asyncio
    @patch("agent_cli.summarizer.adaptive._detailed_summary")
    async def test_detailed_level_calls_detailed_summary(
        self,
        mock_detailed: AsyncMock,
        config: SummarizerConfig,
    ) -> None:
        """Test that DETAILED level content calls _detailed_summary."""
        mock_result = SummaryResult(
            level=SummaryLevel.DETAILED,
            summary="Detailed summary.",
            hierarchical=None,
            input_tokens=5000,
            output_tokens=100,
            compression_ratio=0.02,
        )
        mock_detailed.return_value = mock_result

        # Create content that's ~3000-15000 tokens
        content = "Word " * 5000  # ~5000 tokens

        result = await summarize(content, config)

        assert mock_detailed.called
        assert result.level == SummaryLevel.DETAILED

    @pytest.mark.asyncio
    @patch("agent_cli.summarizer.adaptive._hierarchical_summary")
    async def test_hierarchical_level_calls_hierarchical_summary(
        self,
        mock_hierarchical: AsyncMock,
        config: SummarizerConfig,
    ) -> None:
        """Test that HIERARCHICAL level content calls _hierarchical_summary."""
        mock_result = SummaryResult(
            level=SummaryLevel.HIERARCHICAL,
            summary="Hierarchical summary.",
            hierarchical=None,
            input_tokens=20000,
            output_tokens=500,
            compression_ratio=0.025,
        )
        mock_hierarchical.return_value = mock_result

        # Create content that's > 15000 tokens
        content = "Word " * 20000

        result = await summarize(content, config)

        assert mock_hierarchical.called
        assert result.level == SummaryLevel.HIERARCHICAL


class TestGenerateSummary:
    """Tests for _generate_summary function."""

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

            result = await _generate_summary("Test prompt", config, max_tokens=100)

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
                await _generate_summary("Test prompt", config, max_tokens=100)


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
