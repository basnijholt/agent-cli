"""Adaptive summarization using map-reduce with dynamic collapse.

Implements a simple algorithm inspired by LangChain's map-reduce chains:
1. If content is short enough, summarize directly
2. Otherwise, split into chunks and summarize each (map phase)
3. Recursively collapse summaries until they fit token_max (reduce phase)

Research foundations:
- LangChain ReduceDocumentsChain: token_max=3000, recursive collapse
- BOOOOKSCORE (arXiv:2310.00785): chunk_size=2048 optimal
- Two-phase architecture concept from Mem0 (arXiv:2504.19413)

Key insight: No need for predetermined L1/L2/L3 levels.
Dynamic collapse depth based on actual content length.

See docs/architecture/summarizer.md for detailed design rationale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel

from agent_cli.summarizer._prompts import (
    BRIEF_SUMMARY_PROMPT,
    format_prior_context,
    get_prompt_for_content_type,
)
from agent_cli.summarizer._utils import (
    count_tokens,
    estimate_summary_tokens,
    tokens_to_words,
)
from agent_cli.summarizer.map_reduce import (
    MapReduceConfig,
    MapReduceSummarizationError,
    map_reduce_summarize,
)
from agent_cli.summarizer.models import (
    SummaryLevel,
    SummaryResult,
)

logger = logging.getLogger(__name__)

# Thresholds for summary levels (in tokens)
THRESHOLD_NONE = 100  # Below this, no summary needed
THRESHOLD_BRIEF = 500  # Below this, just a single sentence


class SummaryOutput(BaseModel):
    """Structured output for summary generation."""

    summary: str


class SummarizationError(Exception):
    """Raised when summarization fails after all retries."""


@dataclass
class SummarizerConfig:
    """Configuration for summarization operations.

    Example:
        config = SummarizerConfig(
            openai_base_url="http://localhost:8000/v1",
            model="llama3.1:8b",
        )
        result = await summarize(long_document, config)
        print(f"Level: {result.level.name}")
        print(f"Compression: {result.compression_ratio:.1%}")

    """

    openai_base_url: str
    model: str
    api_key: str | None = None
    chunk_size: int = 2048  # BOOOOKSCORE's tested default
    token_max: int = 3000  # LangChain's default - when to collapse
    chunk_overlap: int = 200
    max_concurrent_chunks: int = 5
    timeout: float = 60.0

    def __post_init__(self) -> None:
        """Normalize the base URL."""
        self.openai_base_url = self.openai_base_url.rstrip("/")
        if self.api_key is None:
            self.api_key = "not-needed"


def determine_level(token_count: int) -> SummaryLevel:
    """Map token count to appropriate SummaryLevel."""
    if token_count < THRESHOLD_NONE:
        return SummaryLevel.NONE
    if token_count < THRESHOLD_BRIEF:
        return SummaryLevel.BRIEF
    return SummaryLevel.MAP_REDUCE


async def summarize(
    content: str,
    config: SummarizerConfig,
    prior_summary: str | None = None,
    content_type: str = "general",
) -> SummaryResult:
    """Summarize content with adaptive strategy based on length.

    Uses a simple algorithm:
    - Very short content (<100 tokens): No summary
    - Short content (<500 tokens): Single sentence brief summary
    - Everything else: Map-reduce with dynamic collapse

    Args:
        content: The content to summarize.
        config: Summarizer configuration.
        prior_summary: Optional prior summary for context continuity.
        content_type: Type of content ("general", "conversation", "journal", "document").

    Returns:
        SummaryResult with summary and metadata.

    """
    if not content or not content.strip():
        return SummaryResult(
            level=SummaryLevel.NONE,
            summary=None,
            input_tokens=0,
            output_tokens=0,
            compression_ratio=0.0,
        )

    input_tokens = count_tokens(content, config.model)
    level = determine_level(input_tokens)

    logger.info(
        "Summarizing %d tokens at level %s (type=%s)",
        input_tokens,
        level.name,
        content_type,
    )

    if level == SummaryLevel.NONE:
        return SummaryResult(
            level=level,
            summary=None,
            input_tokens=input_tokens,
            output_tokens=0,
            compression_ratio=0.0,
        )

    if level == SummaryLevel.BRIEF:
        summary = await _brief_summary(content, config)
        output_tokens = count_tokens(summary, config.model) if summary else 0
        return SummaryResult(
            level=level,
            summary=summary,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            compression_ratio=output_tokens / input_tokens if input_tokens > 0 else 0.0,
        )

    # MAP_REDUCE level
    return await _map_reduce_summary(
        content,
        input_tokens,
        config,
        prior_summary,
        content_type,
    )


async def _brief_summary(content: str, config: SummarizerConfig) -> str:
    """Generate a single-sentence summary for brief content."""
    prompt = BRIEF_SUMMARY_PROMPT.format(content=content)
    return await _generate_summary(prompt, config, max_tokens=50)


async def _map_reduce_summary(
    content: str,
    input_tokens: int,
    config: SummarizerConfig,
    prior_summary: str | None,
    content_type: str,
) -> SummaryResult:
    """Use map-reduce with dynamic collapse for longer content."""
    # For content that fits in a single chunk, use content-type aware summary
    if input_tokens <= config.token_max:
        summary = await _content_aware_summary(content, config, prior_summary, content_type)
        output_tokens = count_tokens(summary, config.model) if summary else 0
        return SummaryResult(
            level=SummaryLevel.MAP_REDUCE,
            summary=summary,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            compression_ratio=output_tokens / input_tokens if input_tokens > 0 else 0.0,
            collapse_depth=0,
        )

    # Use map-reduce for multi-chunk content
    mr_config = MapReduceConfig(
        openai_base_url=config.openai_base_url,
        model=config.model,
        api_key=config.api_key,
        chunk_size=config.chunk_size,
        token_max=config.token_max,
        chunk_overlap=config.chunk_overlap,
        max_concurrent=config.max_concurrent_chunks,
        timeout=config.timeout,
    )

    try:
        result = await map_reduce_summarize(content, mr_config)
    except MapReduceSummarizationError as e:
        raise SummarizationError(str(e)) from e

    return SummaryResult(
        level=SummaryLevel.MAP_REDUCE,
        summary=result.summary,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        compression_ratio=result.compression_ratio,
        collapse_depth=result.collapse_depth,
    )


async def _content_aware_summary(
    content: str,
    config: SummarizerConfig,
    prior_summary: str | None,
    content_type: str,
) -> str:
    """Generate a content-type aware summary for single-chunk content."""
    target_tokens = estimate_summary_tokens(
        count_tokens(content, config.model),
        SummaryLevel.MAP_REDUCE,
    )
    max_words = tokens_to_words(target_tokens)

    prompt_template = get_prompt_for_content_type(content_type)
    prior_context = format_prior_context(prior_summary)

    prompt = prompt_template.format(
        content=content,
        prior_context=prior_context,
        max_words=max_words,
    )

    return await _generate_summary(prompt, config, max_tokens=target_tokens + 50)


async def _generate_summary(
    prompt: str,
    config: SummarizerConfig,
    max_tokens: int = 256,
) -> str:
    """Call the LLM to generate a summary. Raises SummarizationError on failure."""
    from pydantic_ai import Agent  # noqa: PLC0415
    from pydantic_ai.models.openai import OpenAIChatModel  # noqa: PLC0415
    from pydantic_ai.providers.openai import OpenAIProvider  # noqa: PLC0415
    from pydantic_ai.settings import ModelSettings  # noqa: PLC0415

    provider = OpenAIProvider(api_key=config.api_key, base_url=config.openai_base_url)
    model = OpenAIChatModel(
        model_name=config.model,
        provider=provider,
        settings=ModelSettings(
            temperature=0.3,
            max_tokens=max_tokens,
        ),
    )

    agent = Agent(
        model=model,
        system_prompt="You are a concise summarizer. Output only the summary, no preamble.",
        output_type=SummaryOutput,
        retries=2,
    )

    try:
        result = await agent.run(prompt)
        return result.output.summary.strip()
    except Exception as e:
        msg = f"Summarization failed: {e}"
        raise SummarizationError(msg) from e
