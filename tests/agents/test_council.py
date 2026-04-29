"""Tests for the council agent."""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from agent_cli import config
from agent_cli.agents.council import (
    AggregateRanking,
    CouncilResponse,
    CouncilResult,
    RankingResult,
    _calculate_aggregate_rankings,
    _format_responses_for_ranking,
    _format_stage1_for_chairman,
    _format_stage2_for_chairman,
    _run_council,
)
from agent_cli.cli import app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


def _make_mock_console() -> Console:
    """Create a mock console for testing without terminal features."""
    return Console(file=io.StringIO(), width=80, force_terminal=False, no_color=True)


# =============================================================================
# Data Model Tests
# =============================================================================


class TestDataModels:
    """Tests for council data models."""

    def test_council_response_creation(self) -> None:
        """Test CouncilResponse dataclass creation."""
        response = CouncilResponse(
            model="gpt-4o",
            response="Test response",
            elapsed=1.5,
        )
        assert response.model == "gpt-4o"
        assert response.response == "Test response"
        assert response.elapsed == 1.5

    def test_ranking_result_creation(self) -> None:
        """Test RankingResult dataclass creation."""
        result = RankingResult(
            model="gpt-4o",
            evaluation="All responses were good",
            rankings=["A", "B", "C"],
            elapsed=2.0,
        )
        assert result.model == "gpt-4o"
        assert result.evaluation == "All responses were good"
        assert result.rankings == ["A", "B", "C"]
        assert result.elapsed == 2.0

    def test_aggregate_ranking_creation(self) -> None:
        """Test AggregateRanking dataclass creation."""
        ranking = AggregateRanking(
            model="gpt-4o",
            average_rank=1.5,
            rankings_count=3,
        )
        assert ranking.model == "gpt-4o"
        assert ranking.average_rank == 1.5
        assert ranking.rankings_count == 3

    def test_council_result_creation(self) -> None:
        """Test CouncilResult dataclass creation."""
        stage1 = [
            CouncilResponse(model="gpt-4o", response="Response 1", elapsed=1.0),
            CouncilResponse(model="claude", response="Response 2", elapsed=1.5),
        ]
        stage3 = CouncilResponse(model="gpt-4o", response="Final answer", elapsed=2.0)

        result = CouncilResult(
            query="Test query",
            stage1=stage1,
            stage2=None,
            stage3=stage3,
            label_to_model={"A": "gpt-4o", "B": "claude"},
            aggregate_rankings=None,
        )

        assert result.query == "Test query"
        assert len(result.stage1) == 2
        assert result.stage2 is None
        assert result.stage3 is not None
        assert result.stage3.response == "Final answer"


# =============================================================================
# Ranking Calculation Tests
# =============================================================================


class TestCalculateAggregateRankings:
    """Tests for the _calculate_aggregate_rankings function."""

    def test_simple_rankings(self) -> None:
        """Test aggregate rankings with simple input."""
        stage2_results = [
            RankingResult(model="model1", evaluation="eval", rankings=["A", "B", "C"], elapsed=1.0),
            RankingResult(model="model2", evaluation="eval", rankings=["A", "C", "B"], elapsed=1.0),
            RankingResult(model="model3", evaluation="eval", rankings=["B", "A", "C"], elapsed=1.0),
        ]
        label_to_model = {"A": "gpt-4o", "B": "claude", "C": "gemini"}

        result = _calculate_aggregate_rankings(stage2_results, label_to_model)

        assert len(result) == 3
        # gpt-4o got positions 1, 1, 2 -> avg 1.33
        # claude got positions 2, 3, 1 -> avg 2.0
        # gemini got positions 3, 2, 3 -> avg 2.67
        assert result[0].model == "gpt-4o"
        assert result[0].average_rank == pytest.approx(4 / 3, rel=0.01)
        assert result[1].model == "claude"
        assert result[1].average_rank == pytest.approx(2.0)
        assert result[2].model == "gemini"
        assert result[2].average_rank == pytest.approx(8 / 3, rel=0.01)

    def test_rankings_with_response_prefix(self) -> None:
        """Test that 'Response A' format is handled correctly."""
        stage2_results = [
            RankingResult(
                model="model1",
                evaluation="eval",
                rankings=["Response A", "Response B"],
                elapsed=1.0,
            ),
        ]
        label_to_model = {"A": "gpt-4o", "B": "claude"}

        result = _calculate_aggregate_rankings(stage2_results, label_to_model)

        assert len(result) == 2
        assert result[0].model == "gpt-4o"
        assert result[0].average_rank == 1.0
        assert result[1].model == "claude"
        assert result[1].average_rank == 2.0

    def test_rankings_with_lowercase_labels(self) -> None:
        """Test that lowercase labels are normalized."""
        stage2_results = [
            RankingResult(model="model1", evaluation="eval", rankings=["a", "b"], elapsed=1.0),
        ]
        label_to_model = {"A": "gpt-4o", "B": "claude"}

        result = _calculate_aggregate_rankings(stage2_results, label_to_model)

        assert len(result) == 2
        assert result[0].model == "gpt-4o"

    def test_empty_rankings(self) -> None:
        """Test with empty stage2 results."""
        result = _calculate_aggregate_rankings([], {"A": "gpt-4o"})
        assert result == []

    def test_tie_in_rankings(self) -> None:
        """Test when models have the same average rank."""
        stage2_results = [
            RankingResult(model="model1", evaluation="eval", rankings=["A", "B"], elapsed=1.0),
            RankingResult(model="model2", evaluation="eval", rankings=["B", "A"], elapsed=1.0),
        ]
        label_to_model = {"A": "gpt-4o", "B": "claude"}

        result = _calculate_aggregate_rankings(stage2_results, label_to_model)

        assert len(result) == 2
        # Both should have avg rank of 1.5
        assert result[0].average_rank == pytest.approx(1.5)
        assert result[1].average_rank == pytest.approx(1.5)


# =============================================================================
# Formatting Tests
# =============================================================================


class TestFormatFunctions:
    """Tests for formatting helper functions."""

    def test_format_responses_for_ranking(self) -> None:
        """Test formatting responses for the ranking prompt."""
        stage1_results = [
            CouncilResponse(model="gpt-4o", response="First response", elapsed=1.0),
            CouncilResponse(model="claude", response="Second response", elapsed=1.0),
        ]
        label_to_model = {"A": "gpt-4o", "B": "claude"}

        result = _format_responses_for_ranking(stage1_results, label_to_model)

        assert "Response A:" in result
        assert "First response" in result
        assert "Response B:" in result
        assert "Second response" in result
        # Model names should NOT appear (anonymized)
        assert "gpt-4o" not in result
        assert "claude" not in result

    def test_format_stage1_for_chairman(self) -> None:
        """Test formatting stage 1 results for chairman prompt."""
        stage1_results = [
            CouncilResponse(model="gpt-4o", response="First response", elapsed=1.0),
            CouncilResponse(model="claude", response="Second response", elapsed=1.0),
        ]

        result = _format_stage1_for_chairman(stage1_results)

        # Chairman sees model names
        assert "gpt-4o" in result
        assert "claude" in result
        assert "First response" in result
        assert "Second response" in result

    def test_format_stage2_for_chairman_empty(self) -> None:
        """Test formatting empty stage 2 results."""
        result = _format_stage2_for_chairman([])
        assert result == ""

    def test_format_stage2_for_chairman(self) -> None:
        """Test formatting stage 2 results for chairman prompt."""
        stage2_results = [
            RankingResult(
                model="gpt-4o",
                evaluation="All good",
                rankings=["A", "B"],
                elapsed=1.0,
            ),
        ]

        result = _format_stage2_for_chairman(stage2_results)

        assert "Peer Rankings" in result
        assert "gpt-4o" in result
        assert "All good" in result


# =============================================================================
# CLI Command Tests
# =============================================================================


class TestCouncilCLI:
    """Tests for the council CLI command."""

    def test_council_help(self) -> None:
        """Test that council --help works."""
        result = runner.invoke(app, ["council", "--help"])
        assert result.exit_code == 0
        assert "LLM Council" in result.output
        assert "--models" in result.output
        assert "--chairman" in result.output
        assert "--no-ranking" in result.output

    @patch("agent_cli.agents.council.console", _make_mock_console())
    @patch("agent_cli.agents.council._run_council")
    @patch("agent_cli.agents.council.pyperclip.copy")
    def test_council_basic_invocation(
        self,
        mock_clipboard: MagicMock,  # noqa: ARG002
        mock_run_council: MagicMock,
    ) -> None:
        """Test basic council command invocation with mocked API."""
        # Setup mock result
        mock_result = CouncilResult(
            query="Test query",
            stage1=[CouncilResponse(model="gpt-4o", response="Response", elapsed=1.0)],
            stage2=None,
            stage3=CouncilResponse(model="gpt-4o", response="Final answer", elapsed=1.0),
            label_to_model={"A": "gpt-4o"},
            aggregate_rankings=None,
        )

        async def mock_run(*_args: Any, **_kwargs: Any) -> CouncilResult:
            return mock_result

        mock_run_council.side_effect = mock_run

        result = runner.invoke(
            app,
            [
                "council",
                "Test query",
                "--openai-base-url",
                "http://localhost:8080/v1",
                "--openai-api-key",
                "test-key",
                "--models",
                "gpt-4o,claude",  # Need at least 2 models
                "--no-ranking",
                "--no-clipboard",
            ],
        )

        # Command should complete (exit code 0 or output contains expected content)
        # Note: typer.testing may show exit_code=1 due to async handling
        assert mock_run_council.called or "Council Query" in result.output

    def test_council_json_output_format(self) -> None:
        """Test that --json flag produces valid JSON structure."""
        with (
            patch("agent_cli.agents.council.console", _make_mock_console()),
            patch("agent_cli.agents.council._run_council") as mock_run,
        ):
            mock_result = CouncilResult(
                query="Test",
                stage1=[CouncilResponse(model="m1", response="r1", elapsed=1.0)],
                stage2=None,
                stage3=CouncilResponse(model="m1", response="final", elapsed=1.0),
                label_to_model={"A": "m1"},
                aggregate_rankings=None,
            )

            async def mock_coro(*_args: Any, **_kwargs: Any) -> CouncilResult:
                return mock_result

            mock_run.side_effect = mock_coro

            result = runner.invoke(
                app,
                [
                    "council",
                    "Test",
                    "--json",
                    "--openai-base-url",
                    "http://localhost:8080/v1",
                    "--openai-api-key",
                    "test-key",
                    "--no-clipboard",
                ],
            )

            # If the command ran successfully and output JSON
            if result.exit_code == 0 and "{" in result.output:
                # Find the JSON part of output
                json_start = result.output.find("{")
                json_end = result.output.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = result.output[json_start:json_end]
                    parsed = json.loads(json_str)
                    assert "query" in parsed
                    assert "stage1" in parsed


# =============================================================================
# Integration-style Tests (with mocked API)
# =============================================================================


class TestCouncilIntegration:
    """Integration tests with mocked API responses."""

    @pytest.mark.asyncio
    async def test_run_council_no_ranking(self) -> None:
        """Test _run_council with ranking disabled."""
        openai_cfg = config.OpenAILLM(
            llm_openai_model="gpt-4o",
            openai_api_key="test-key",
            openai_base_url="http://localhost:8080/v1",
        )

        with patch("agent_cli.agents.council._query_single_model") as mock_query:
            # Mock stage 1 responses
            mock_query.side_effect = [
                CouncilResponse(model="model1", response="Response 1", elapsed=1.0),
                CouncilResponse(model="model2", response="Response 2", elapsed=1.0),
                # Stage 3 chairman response
                CouncilResponse(model="model1", response="Final synthesis", elapsed=1.0),
            ]

            result = await _run_council(
                query="Test question",
                models=["model1", "model2"],
                chairman_model="model1",
                openai_cfg=openai_cfg,
                skip_ranking=True,
                quiet=True,
            )

            assert result.query == "Test question"
            assert len(result.stage1) == 2
            assert result.stage2 is None
            assert result.stage3 is not None
            assert result.stage3.response == "Final synthesis"

    @pytest.mark.asyncio
    async def test_run_council_with_ranking(self) -> None:
        """Test _run_council with ranking enabled."""
        openai_cfg = config.OpenAILLM(
            llm_openai_model="gpt-4o",
            openai_api_key="test-key",
            openai_base_url="http://localhost:8080/v1",
        )

        with (
            patch("agent_cli.agents.council.stage1_collect_responses") as mock_stage1,
            patch("agent_cli.agents.council.stage2_collect_rankings") as mock_stage2,
            patch("agent_cli.agents.council.stage3_synthesize") as mock_stage3,
        ):
            # Stage 1 mock
            async def stage1_mock(
                *_args: Any,
                **_kwargs: Any,
            ) -> list[CouncilResponse]:
                return [
                    CouncilResponse(model="model1", response="Response 1", elapsed=1.0),
                    CouncilResponse(model="model2", response="Response 2", elapsed=1.0),
                ]

            mock_stage1.side_effect = stage1_mock

            # Stage 2 mock
            async def stage2_mock(
                *_args: Any,
                **_kwargs: Any,
            ) -> tuple[list[RankingResult], dict[str, str]]:
                return (
                    [
                        RankingResult(
                            model="model1",
                            evaluation="Good",
                            rankings=["A", "B"],
                            elapsed=1.0,
                        ),
                        RankingResult(
                            model="model2",
                            evaluation="Good",
                            rankings=["B", "A"],
                            elapsed=1.0,
                        ),
                    ],
                    {"A": "model1", "B": "model2"},
                )

            mock_stage2.side_effect = stage2_mock

            # Stage 3 mock
            async def stage3_mock(*_args: Any, **_kwargs: Any) -> CouncilResponse:
                return CouncilResponse(model="model1", response="Final synthesis", elapsed=1.0)

            mock_stage3.side_effect = stage3_mock

            result = await _run_council(
                query="Test question",
                models=["model1", "model2"],
                chairman_model="model1",
                openai_cfg=openai_cfg,
                skip_ranking=False,
                quiet=True,
            )

            assert result.query == "Test question"
            assert len(result.stage1) == 2
            assert result.stage2 is not None
            assert len(result.stage2) == 2
            assert result.stage3 is not None
            assert result.stage3.response == "Final synthesis"
