"""LLM Council - Multi-model deliberation with peer review and synthesis."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pyperclip
import typer
from pydantic import BaseModel, Field
from rich.panel import Panel
from rich.table import Table

from agent_cli import config, opts
from agent_cli.cli import app
from agent_cli.core.utils import (
    console,
    print_command_line_args,
    print_error_message,
    print_input_panel,
    setup_logging,
)

if TYPE_CHECKING:
    from pydantic_ai import Agent

LOGGER = logging.getLogger(__name__)

# =============================================================================
# Pydantic Models for Structured Output
# =============================================================================


class RankingEntry(BaseModel):
    """A single ranking entry with response label and brief reasoning."""

    response_label: str = Field(description="The response label (e.g., 'A', 'B', 'C')")
    reasoning: str = Field(description="Brief explanation for this ranking position")


class RankingOutput(BaseModel):
    """Structured ranking output from a model."""

    evaluation: str = Field(description="Overall evaluation of all responses")
    rankings: list[RankingEntry] = Field(
        description="Ordered list from best to worst response",
    )


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class CouncilResponse:
    """A response from a single model."""

    model: str
    response: str
    elapsed: float = 0.0


@dataclass
class RankingResult:
    """A ranking evaluation from a single model."""

    model: str
    evaluation: str
    rankings: list[str] = field(default_factory=list)  # List of response labels
    elapsed: float = 0.0


@dataclass
class AggregateRanking:
    """Aggregate ranking for a model across all peer evaluations."""

    model: str
    average_rank: float
    rankings_count: int


@dataclass
class CouncilResult:
    """Complete result from running the council."""

    query: str
    stage1: list[CouncilResponse]
    stage2: list[RankingResult] | None
    stage3: CouncilResponse | None
    label_to_model: dict[str, str]
    aggregate_rankings: list[AggregateRanking] | None = None


# =============================================================================
# Prompts
# =============================================================================

STAGE1_SYSTEM_PROMPT = """You are a helpful AI assistant participating in a council of AI models.
Answer the user's question thoughtfully and comprehensively.
Your response will be evaluated alongside responses from other AI models."""

RANKING_SYSTEM_PROMPT = """You are an impartial evaluator assessing the quality of different AI responses.
Evaluate each response carefully and provide a ranking from best to worst."""

RANKING_USER_PROMPT = """Evaluate the following responses to this question:

Question: {query}

Responses (anonymized):

{formatted_responses}

Provide:
1. An overall evaluation discussing the strengths and weaknesses of each response
2. A ranking from best to worst, using the response labels (A, B, C, etc.)"""

CHAIRMAN_SYSTEM_PROMPT = """You are the Chairman of an LLM Council.
Your role is to synthesize multiple perspectives into a single, comprehensive answer."""

CHAIRMAN_USER_PROMPT = """You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {query}

STAGE 1 - Individual Responses:
{formatted_stage1}

{stage2_section}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""


# =============================================================================
# Helper Functions
# =============================================================================


def _create_model_agent(
    model_name: str,
    openai_cfg: config.OpenAILLM,
    system_prompt: str,
    output_type: type | None = None,
) -> Agent:
    """Create a PydanticAI agent for a specific model."""
    from pydantic_ai import Agent  # noqa: PLC0415
    from pydantic_ai.models.openai import OpenAIChatModel  # noqa: PLC0415
    from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415

    provider = OpenAIProvider(
        api_key=openai_cfg.openai_api_key or "dummy",
        base_url=openai_cfg.openai_base_url,
    )
    model = OpenAIChatModel(model_name=model_name, provider=provider)

    kwargs: dict = {
        "model": model,
        "system_prompt": system_prompt,
    }
    if output_type is not None:
        kwargs["output_type"] = output_type

    return Agent(**kwargs)


def _calculate_aggregate_rankings(
    stage2_results: list[RankingResult],
    label_to_model: dict[str, str],
) -> list[AggregateRanking]:
    """Calculate aggregate rankings from peer evaluations.

    Returns list of models sorted by average rank (lower is better).
    """
    model_scores: dict[str, list[int]] = {model: [] for model in label_to_model.values()}

    for result in stage2_results:
        for position, label in enumerate(result.rankings, start=1):
            # Normalize label (handle "A", "Response A", etc.)
            clean_label = label.strip().upper()
            clean_label = clean_label.removeprefix("RESPONSE ")
            if clean_label in label_to_model:
                model = label_to_model[clean_label]
                model_scores[model].append(position)

    rankings = []
    for model, scores in model_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            rankings.append(
                AggregateRanking(model=model, average_rank=avg, rankings_count=len(scores)),
            )

    rankings.sort(key=lambda x: x.average_rank)
    return rankings


def _format_responses_for_ranking(
    stage1_results: list[CouncilResponse],
    label_to_model: dict[str, str],
) -> str:
    """Format stage 1 responses for the ranking prompt with anonymized labels."""
    model_to_label = {v: k for k, v in label_to_model.items()}
    parts = []
    for response in stage1_results:
        label = model_to_label.get(response.model, "?")
        parts.append(f"Response {label}:\n{response.response}")
    return "\n\n".join(parts)


def _format_stage1_for_chairman(stage1_results: list[CouncilResponse]) -> str:
    """Format stage 1 responses for the chairman prompt."""
    parts = [
        f"Model: {response.model}\nResponse: {response.response}" for response in stage1_results
    ]
    return "\n\n".join(parts)


def _format_stage2_for_chairman(
    stage2_results: list[RankingResult],
) -> str:
    """Format stage 2 rankings for the chairman prompt."""
    if not stage2_results:
        return ""

    parts = ["STAGE 2 - Peer Rankings:"]
    for result in stage2_results:
        ranking_str = ", ".join(f"{i}. {label}" for i, label in enumerate(result.rankings, start=1))
        parts.append(f"\nModel: {result.model}\nRanking: {ranking_str}")
        parts.append(f"Evaluation: {result.evaluation}")

    return "\n".join(parts)


# =============================================================================
# Stage Functions
# =============================================================================


async def _query_single_model(
    model_name: str,
    user_prompt: str,
    openai_cfg: config.OpenAILLM,
    system_prompt: str,
) -> CouncilResponse | None:
    """Query a single model and return the response."""
    start = time.monotonic()
    try:
        agent = _create_model_agent(model_name, openai_cfg, system_prompt)
        result = await agent.run(user_prompt)
        elapsed = time.monotonic() - start
        return CouncilResponse(model=model_name, response=result.output, elapsed=elapsed)
    except Exception:
        LOGGER.warning("Model %s failed", model_name, exc_info=True)
        return None


async def _query_single_model_ranking(
    model_name: str,
    user_prompt: str,
    openai_cfg: config.OpenAILLM,
    system_prompt: str,
) -> RankingResult | None:
    """Query a single model for ranking using structured output."""
    start = time.monotonic()
    try:
        agent = _create_model_agent(
            model_name,
            openai_cfg,
            system_prompt,
            output_type=RankingOutput,
        )
        result = await agent.run(user_prompt)
        elapsed = time.monotonic() - start

        # Extract rankings from structured output
        output: RankingOutput = result.output
        rankings = [entry.response_label for entry in output.rankings]

        return RankingResult(
            model=model_name,
            evaluation=output.evaluation,
            rankings=rankings,
            elapsed=elapsed,
        )
    except Exception:
        LOGGER.warning("Model %s ranking failed", model_name, exc_info=True)
        return None


async def stage1_collect_responses(
    query: str,
    models: list[str],
    openai_cfg: config.OpenAILLM,
    quiet: bool = False,
) -> list[CouncilResponse]:
    """Collect responses from all council models in parallel."""
    if not quiet:
        console.print(f"\n[bold cyan]Stage 1:[/bold cyan] Querying {len(models)} models...")

    tasks = [
        _query_single_model(model, query, openai_cfg, STAGE1_SYSTEM_PROMPT) for model in models
    ]
    results = await asyncio.gather(*tasks)

    # Filter out failed models
    responses = [r for r in results if r is not None]

    if not quiet:
        for r in responses:
            console.print(f"  [green]✓[/green] {r.model} ({r.elapsed:.1f}s)")
        failed = len(models) - len(responses)
        if failed > 0:
            console.print(f"  [yellow]⚠[/yellow] {failed} model(s) failed")

    return responses


async def stage2_collect_rankings(
    query: str,
    stage1_results: list[CouncilResponse],
    models: list[str],
    openai_cfg: config.OpenAILLM,
    quiet: bool = False,
) -> tuple[list[RankingResult], dict[str, str]]:
    """Have each model rank the anonymized responses using structured output."""
    if not quiet:
        console.print("\n[bold cyan]Stage 2:[/bold cyan] Collecting peer rankings...")

    # Create anonymized labels (A, B, C, ...)
    label_to_model = {chr(65 + i): r.model for i, r in enumerate(stage1_results)}

    # Format the ranking prompt
    formatted_responses = _format_responses_for_ranking(stage1_results, label_to_model)
    ranking_prompt = RANKING_USER_PROMPT.format(
        query=query,
        formatted_responses=formatted_responses,
    )

    # Query all models for rankings using structured output
    tasks = [
        _query_single_model_ranking(model, ranking_prompt, openai_cfg, RANKING_SYSTEM_PROMPT)
        for model in models
    ]
    results = await asyncio.gather(*tasks)

    # Filter out failed models
    ranking_results = [r for r in results if r is not None]

    if not quiet:
        for r in ranking_results:
            console.print(f"  [green]✓[/green] {r.model} ({r.elapsed:.1f}s)")

    return ranking_results, label_to_model


async def stage3_synthesize(
    query: str,
    stage1_results: list[CouncilResponse],
    stage2_results: list[RankingResult] | None,
    chairman_model: str,
    openai_cfg: config.OpenAILLM,
    quiet: bool = False,
) -> CouncilResponse | None:
    """Have the chairman synthesize a final answer."""
    if not quiet:
        console.print(
            f"\n[bold cyan]Stage 3:[/bold cyan] Chairman ({chairman_model}) synthesizing...",
        )

    # Format the chairman prompt
    formatted_stage1 = _format_stage1_for_chairman(stage1_results)
    stage2_section = ""
    if stage2_results:
        stage2_section = _format_stage2_for_chairman(stage2_results)

    chairman_prompt = CHAIRMAN_USER_PROMPT.format(
        query=query,
        formatted_stage1=formatted_stage1,
        stage2_section=stage2_section,
    )

    result = await _query_single_model(
        chairman_model,
        chairman_prompt,
        openai_cfg,
        CHAIRMAN_SYSTEM_PROMPT,
    )

    if result and not quiet:
        console.print(f"  [green]✓[/green] Chairman complete ({result.elapsed:.1f}s)")

    return result


async def run_council(
    query: str,
    models: list[str],
    chairman_model: str,
    openai_cfg: config.OpenAILLM,
    skip_ranking: bool = False,
    quiet: bool = False,
) -> CouncilResult:
    """Run the full council deliberation process."""
    # Stage 1: Collect responses
    stage1_results = await stage1_collect_responses(
        query=query,
        models=models,
        openai_cfg=openai_cfg,
        quiet=quiet,
    )

    min_models = 2
    if len(stage1_results) < min_models:
        msg = f"Need at least {min_models} successful responses, got {len(stage1_results)}"
        raise ValueError(msg)

    # Create label mapping
    label_to_model = {chr(65 + i): r.model for i, r in enumerate(stage1_results)}

    # Stage 2: Collect rankings (optional)
    stage2_results = None
    aggregate_rankings = None
    if not skip_ranking:
        stage2_results, label_to_model = await stage2_collect_rankings(
            query=query,
            stage1_results=stage1_results,
            models=models,
            openai_cfg=openai_cfg,
            quiet=quiet,
        )
        if stage2_results:
            aggregate_rankings = _calculate_aggregate_rankings(stage2_results, label_to_model)

    # Stage 3: Chairman synthesis
    stage3_result = await stage3_synthesize(
        query=query,
        stage1_results=stage1_results,
        stage2_results=stage2_results,
        chairman_model=chairman_model,
        openai_cfg=openai_cfg,
        quiet=quiet,
    )

    return CouncilResult(
        query=query,
        stage1=stage1_results,
        stage2=stage2_results,
        stage3=stage3_result,
        label_to_model=label_to_model,
        aggregate_rankings=aggregate_rankings,
    )


# =============================================================================
# Output Rendering
# =============================================================================


def _render_stage1(result: CouncilResult) -> None:
    """Render Stage 1 responses."""
    console.print("\n[bold green]━━━ Stage 1: Individual Responses ━━━[/bold green]\n")

    for response in result.stage1:
        panel = Panel(
            response.response,
            title=f"[bold]🤖 {response.model}[/bold]",
            subtitle=f"[dim]{response.elapsed:.1f}s[/dim]",
            border_style="blue",
        )
        console.print(panel)
        console.print()


def _render_stage2(result: CouncilResult) -> None:
    """Render Stage 2 rankings."""
    if not result.stage2 or not result.aggregate_rankings:
        return

    console.print('\n[bold green]━━━ Stage 2: Peer Rankings ("Street Cred") ━━━[/bold green]\n')

    # Show aggregate rankings table
    table = Table(title="Aggregate Rankings", show_header=True, header_style="bold magenta")
    table.add_column("Rank", style="cyan", justify="center")
    table.add_column("Model", style="white")
    table.add_column("Avg Score", style="yellow", justify="center")
    table.add_column("Votes", style="dim", justify="center")

    for i, ranking in enumerate(result.aggregate_rankings, start=1):
        table.add_row(
            f"#{i}",
            ranking.model,
            f"{ranking.average_rank:.2f}",
            str(ranking.rankings_count),
        )

    console.print(table)
    console.print()


def _render_stage3(result: CouncilResult) -> None:
    """Render Stage 3 final answer."""
    if not result.stage3:
        return

    console.print("\n[bold green]━━━ Final Answer ━━━[/bold green]\n")

    panel = Panel(
        result.stage3.response,
        title=f"[bold]👑 Chairman: {result.stage3.model}[/bold]",
        subtitle=f"[dim]{result.stage3.elapsed:.1f}s[/dim]",
        border_style="green",
    )
    console.print(panel)


def render_council_result(
    result: CouncilResult,
    *,
    final_only: bool = False,
    json_output: bool = False,
) -> None:
    """Render the complete council result."""
    if json_output:
        output = {
            "query": result.query,
            "stage1": [
                {"model": r.model, "response": r.response, "elapsed": r.elapsed}
                for r in result.stage1
            ],
            "stage2": (
                [
                    {
                        "model": r.model,
                        "evaluation": r.evaluation,
                        "rankings": r.rankings,
                        "elapsed": r.elapsed,
                    }
                    for r in result.stage2
                ]
                if result.stage2
                else None
            ),
            "stage3": (
                {
                    "model": result.stage3.model,
                    "response": result.stage3.response,
                    "elapsed": result.stage3.elapsed,
                }
                if result.stage3
                else None
            ),
            "label_to_model": result.label_to_model,
            "aggregate_rankings": (
                [
                    {
                        "model": r.model,
                        "average_rank": r.average_rank,
                        "rankings_count": r.rankings_count,
                    }
                    for r in result.aggregate_rankings
                ]
                if result.aggregate_rankings
                else None
            ),
        }
        console.print_json(json.dumps(output, indent=2))
        return

    # Show query
    print_input_panel(result.query, title="Council Query")

    if final_only:
        _render_stage3(result)
    else:
        _render_stage1(result)
        _render_stage2(result)
        _render_stage3(result)


# =============================================================================
# CLI Command
# =============================================================================


async def _async_council(
    query: str,
    models: list[str],
    chairman: str,
    openai_cfg: config.OpenAILLM,
    skip_ranking: bool,
    final_only: bool,
    json_output: bool,
    clipboard: bool,
    quiet: bool,
) -> None:
    """Async implementation of the council command."""
    result = await run_council(
        query=query,
        models=models,
        chairman_model=chairman,
        openai_cfg=openai_cfg,
        skip_ranking=skip_ranking,
        quiet=quiet or json_output,
    )

    # Render output
    render_council_result(result, final_only=final_only, json_output=json_output)

    # Copy final answer to clipboard
    if clipboard and result.stage3:
        pyperclip.copy(result.stage3.response)
        if not quiet and not json_output:
            console.print("\n[dim]✓ Final answer copied to clipboard[/dim]")


@app.command("council")
def council(
    query: str | None = typer.Argument(
        None,
        help="Query for the council (reads from clipboard if not provided).",
    ),
    # Model selection
    models: str = typer.Option(
        "gpt-4o,claude-sonnet-4,gemini-2.0-flash",
        "--models",
        "-m",
        help="Comma-separated list of models to query.",
        rich_help_panel="Model Selection",
    ),
    chairman: str | None = typer.Option(
        None,
        "--chairman",
        "-c",
        help="Model to use as chairman (default: first model in list).",
        rich_help_panel="Model Selection",
    ),
    # Stage control
    no_ranking: bool = typer.Option(
        False,  # noqa: FBT003
        "--no-ranking",
        help="Skip peer ranking stage (faster, 2-stage only).",
        rich_help_panel="Stage Control",
    ),
    # Output options
    final_only: bool = typer.Option(
        False,  # noqa: FBT003
        "--final-only",
        help="Show only final answer (hide individual responses and rankings).",
        rich_help_panel="Output Options",
    ),
    json_output: bool = typer.Option(
        False,  # noqa: FBT003
        "--json",
        "-j",
        help="Output as JSON.",
        rich_help_panel="Output Options",
    ),
    clipboard: bool = typer.Option(
        True,  # noqa: FBT003
        "--clipboard/--no-clipboard",
        help="Copy final answer to clipboard.",
        rich_help_panel="Output Options",
    ),
    # OpenAI-compatible API options
    openai_api_key: str | None = opts.OPENAI_API_KEY,
    openai_base_url: str | None = opts.OPENAI_BASE_URL,
    # General options
    log_level: str = opts.LOG_LEVEL,
    log_file: str | None = opts.LOG_FILE,
    quiet: bool = opts.QUIET,
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    r"""Run an LLM Council for collaborative AI deliberation.

    Sends a prompt to multiple models, has them peer-review each other's
    responses, then synthesizes a final answer through a chairman model.

    Examples:
        # Basic usage with OpenRouter
        agent-cli council "What is the best way to learn programming?" \
            --openai-base-url https://openrouter.ai/api/v1 \
            --openai-api-key sk-or-...

        # Custom models
        agent-cli council "..." --models "gpt-4o,claude-3-opus,gemini-1.5-pro"

        # Skip ranking for faster results
        agent-cli council "..." --no-ranking

        # Output as JSON
        agent-cli council "..." --json

    """
    if print_args:
        print_command_line_args(locals())

    setup_logging(log_level, log_file, quiet=quiet)

    # Get query from clipboard if not provided
    if query is None:
        try:
            query = pyperclip.paste()
            if not query or not query.strip():
                print_error_message("No query provided and clipboard is empty.")
                raise typer.Exit(1)
        except pyperclip.PyperclipException as e:
            print_error_message(f"Failed to read clipboard: {e}")
            raise typer.Exit(1) from e

    # Parse models list
    model_list = [m.strip() for m in models.split(",") if m.strip()]
    min_models = 2
    if len(model_list) < min_models:
        print_error_message(f"At least {min_models} models are required for the council.")
        raise typer.Exit(1)

    # Set chairman (default to first model)
    chairman_model = chairman if chairman else model_list[0]

    # Create OpenAI config
    openai_cfg = config.OpenAILLM(
        llm_openai_model=chairman_model,  # Not used directly, but required
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
    )

    # Validate API key
    if not openai_cfg.openai_api_key and not openai_cfg.openai_base_url:
        print_error_message(
            "OpenAI API key required. Set --openai-api-key or OPENAI_API_KEY env var.",
            "For OpenRouter, also set --openai-base-url https://openrouter.ai/api/v1",
        )
        raise typer.Exit(1)

    try:
        asyncio.run(
            _async_council(
                query=query,
                models=model_list,
                chairman=chairman_model,
                openai_cfg=openai_cfg,
                skip_ranking=no_ranking,
                final_only=final_only,
                json_output=json_output,
                clipboard=clipboard,
                quiet=quiet,
            ),
        )
    except ValueError as e:
        print_error_message(str(e))
        raise typer.Exit(1) from e
    except Exception as e:
        LOGGER.exception("Council failed")
        print_error_message(f"Council failed: {e}")
        raise typer.Exit(1) from e
