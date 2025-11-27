"""Adaptive summarization that scales with input complexity.

This module implements research-grounded summarization inspired by:
- Letta: Partial eviction (30%), middle truncation, fire-and-forget background processing
- Mem0: Rolling summaries, 90%+ compression, two-phase architecture

Reference: arXiv:2504.19413 (Mem0), arXiv:2310.08560 (MemGPT/Letta)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from agent_cli.summarizer.models import (
    ChunkSummary,
    HierarchicalSummary,
    SummaryLevel,
    SummaryResult,
)
from agent_cli.summarizer.prompts import (
    BRIEF_SUMMARY_PROMPT,
    CHUNK_SUMMARY_PROMPT,
    META_SUMMARY_PROMPT,
    ROLLING_SUMMARY_PROMPT,
    format_prior_context,
    format_summaries_for_meta,
    get_prompt_for_content_type,
)
from agent_cli.summarizer.utils import (
    chunk_text,
    count_tokens,
    estimate_summary_tokens,
    middle_truncate,
    tokens_to_words,
)

logger = logging.getLogger(__name__)

# Thresholds for summary levels (in tokens)
LEVEL_THRESHOLDS = {
    SummaryLevel.NONE: 100,
    SummaryLevel.BRIEF: 500,
    SummaryLevel.STANDARD: 3000,
    SummaryLevel.DETAILED: 15000,
    # HIERARCHICAL is everything above DETAILED
}

# Number of L1 chunks to group together for L2 summaries
L2_GROUP_SIZE = 5
# Minimum number of L1 chunks before L2 grouping is applied
L2_MIN_CHUNKS = 5

# Retry settings for summarization failures
MAX_SUMMARIZE_RETRIES = 3

# Maximum characters per chunk before applying middle truncation
# This prevents context overflow errors for very large chunks
# (roughly 12K tokens with cl100k_base encoding)
MAX_CHUNK_CHARS = 48000


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
    chunk_size: int = 3000
    chunk_overlap: int = 200
    max_concurrent_chunks: int = 5
    timeout: float = 60.0

    def __post_init__(self) -> None:
        """Normalize the base URL."""
        self.openai_base_url = self.openai_base_url.rstrip("/")
        if self.api_key is None:
            self.api_key = "not-needed"


def determine_level(token_count: int) -> SummaryLevel:
    """Determine the appropriate summary level based on token count.

    Args:
        token_count: Number of tokens in the input.

    Returns:
        The recommended SummaryLevel.

    """
    if token_count < LEVEL_THRESHOLDS[SummaryLevel.NONE]:
        return SummaryLevel.NONE
    if token_count < LEVEL_THRESHOLDS[SummaryLevel.BRIEF]:
        return SummaryLevel.BRIEF
    if token_count < LEVEL_THRESHOLDS[SummaryLevel.STANDARD]:
        return SummaryLevel.STANDARD
    if token_count < LEVEL_THRESHOLDS[SummaryLevel.DETAILED]:
        return SummaryLevel.DETAILED
    return SummaryLevel.HIERARCHICAL


async def summarize(
    content: str,
    config: SummarizerConfig,
    prior_summary: str | None = None,
    content_type: str = "general",
) -> SummaryResult:
    """Summarize content with adaptive strategy based on length.

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
            hierarchical=None,
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
            hierarchical=None,
            input_tokens=input_tokens,
            output_tokens=0,
            compression_ratio=0.0,
        )

    if level == SummaryLevel.BRIEF:
        summary = await _brief_summary(content, config)
    elif level == SummaryLevel.STANDARD:
        summary = await _standard_summary(content, config, prior_summary, content_type)
    elif level == SummaryLevel.DETAILED:
        return await _detailed_summary(content, input_tokens, config)
    else:  # HIERARCHICAL
        return await _hierarchical_summary(content, input_tokens, config)

    output_tokens = count_tokens(summary, config.model) if summary else 0
    compression_ratio = output_tokens / input_tokens if input_tokens > 0 else 0.0

    return SummaryResult(
        level=level,
        summary=summary,
        hierarchical=None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        compression_ratio=compression_ratio,
    )


async def update_rolling_summary(
    prior_summary: str | None,
    new_facts: list[str],
    config: SummarizerConfig,
) -> str:
    """Update a rolling summary with new facts (Mem0-style).

    This is optimized for incremental updates where you have discrete
    new facts to integrate into an existing summary.

    Args:
        prior_summary: The existing summary to update.
        new_facts: List of new facts to integrate.
        config: Summarizer configuration.

    Returns:
        Updated summary string.

    """
    if not new_facts:
        return prior_summary or ""

    new_content = "\n".join(f"- {fact}" for fact in new_facts)
    combined_tokens = count_tokens(
        (prior_summary or "") + new_content,
        config.model,
    )

    target_tokens = estimate_summary_tokens(combined_tokens, SummaryLevel.STANDARD)
    max_words = tokens_to_words(target_tokens)

    prompt = ROLLING_SUMMARY_PROMPT.format(
        prior_summary=prior_summary or "(No prior summary)",
        new_content=new_content,
        max_words=max_words,
    )

    return await _generate_summary(prompt, config, max_tokens=target_tokens + 50)


async def _summarize_single_chunk(
    chunk: str,
    chunk_index: int,
    total_chunks: int,
    config: SummarizerConfig,
    *,
    parent_group: int | None = None,
) -> ChunkSummary:
    """Summarize a single chunk of content.

    Uses middle truncation as a fallback for oversized content (Letta-style).

    Args:
        chunk: The text chunk to summarize.
        chunk_index: Index of this chunk (0-based).
        total_chunks: Total number of chunks being processed.
        config: Summarizer configuration.
        parent_group: Optional L2 group index for hierarchical summaries.

    Returns:
        ChunkSummary with the summarized content.

    """
    # Apply middle truncation if chunk is too large (Letta-style fallback)
    source_tokens = count_tokens(chunk, config.model)
    content_to_summarize = chunk
    if len(chunk) > MAX_CHUNK_CHARS:
        content_to_summarize, dropped = middle_truncate(
            chunk,
            MAX_CHUNK_CHARS,
            head_frac=0.3,
            tail_frac=0.3,
        )
        logger.warning(
            "Chunk %d truncated: dropped %d chars to fit context window",
            chunk_index,
            dropped,
        )

    chunk_tokens = count_tokens(content_to_summarize, config.model)
    target_tokens = estimate_summary_tokens(chunk_tokens, SummaryLevel.STANDARD)
    max_words = tokens_to_words(target_tokens)

    prompt = CHUNK_SUMMARY_PROMPT.format(
        chunk_index=chunk_index + 1,
        total_chunks=total_chunks,
        content=content_to_summarize,
        max_words=max_words,
    )

    summary = await _generate_summary(prompt, config, max_tokens=target_tokens + 50)
    summary_tokens = count_tokens(summary, config.model)

    return ChunkSummary(
        chunk_index=chunk_index,
        content=summary,
        token_count=summary_tokens,
        source_tokens=source_tokens,  # Report original token count
        parent_group=parent_group,
    )


async def _brief_summary(content: str, config: SummarizerConfig) -> str:
    """Generate a single-sentence summary for brief content."""
    prompt = BRIEF_SUMMARY_PROMPT.format(content=content)
    return await _generate_summary(prompt, config, max_tokens=50)


async def _standard_summary(
    content: str,
    config: SummarizerConfig,
    prior_summary: str | None,
    content_type: str,
) -> str:
    """Generate a paragraph summary for standard-length content."""
    input_tokens = count_tokens(content, config.model)
    target_tokens = estimate_summary_tokens(input_tokens, SummaryLevel.STANDARD)
    max_words = tokens_to_words(target_tokens)

    prompt_template = get_prompt_for_content_type(content_type)
    prior_context = format_prior_context(prior_summary)

    prompt = prompt_template.format(
        content=content,
        prior_context=prior_context,
        max_words=max_words,
    )

    return await _generate_summary(prompt, config, max_tokens=target_tokens + 50)


async def _detailed_summary(
    content: str,
    input_tokens: int,
    config: SummarizerConfig,
) -> SummaryResult:
    """Generate chunked summaries with meta-summary for detailed content."""
    chunks = chunk_text(
        content,
        chunk_size=config.chunk_size,
        overlap=config.chunk_overlap,
        model=config.model,
    )

    logger.info("Detailed summary: processing %d chunks", len(chunks))

    # Summarize chunks (with concurrency limit)
    semaphore = asyncio.Semaphore(config.max_concurrent_chunks)

    async def summarize_with_limit(idx: int, chunk: str) -> ChunkSummary:
        async with semaphore:
            return await _summarize_single_chunk(
                chunk,
                idx,
                len(chunks),
                config,
                parent_group=None,
            )

    chunk_summaries = await asyncio.gather(
        *[summarize_with_limit(i, chunk) for i, chunk in enumerate(chunks)],
    )

    # Generate meta-summary
    all_summaries = [cs.content for cs in chunk_summaries]
    meta_target = estimate_summary_tokens(input_tokens, SummaryLevel.DETAILED)
    max_words = tokens_to_words(meta_target)

    meta_prompt = META_SUMMARY_PROMPT.format(
        summaries=format_summaries_for_meta(all_summaries),
        max_words=max_words,
    )

    final_summary = await _generate_summary(
        meta_prompt,
        config,
        max_tokens=meta_target + 100,
    )
    output_tokens = count_tokens(final_summary, config.model)

    hierarchical = HierarchicalSummary(
        l1_summaries=list(chunk_summaries),
        l2_summaries=[],  # Not used for DETAILED level
        l3_summary=final_summary,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )

    return SummaryResult(
        level=SummaryLevel.DETAILED,
        summary=final_summary,
        hierarchical=hierarchical,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        compression_ratio=output_tokens / input_tokens if input_tokens > 0 else 0.0,
    )


async def _hierarchical_summary(
    content: str,
    input_tokens: int,
    config: SummarizerConfig,
) -> SummaryResult:
    """Build a tree of summaries for very long content.

    Structure:
    - L1: Individual chunk summaries
    - L2: Group summaries (groups of ~5 L1 summaries)
    - L3: Final synthesis
    """
    chunks = chunk_text(
        content,
        chunk_size=config.chunk_size,
        overlap=config.chunk_overlap,
        model=config.model,
    )

    logger.info("Hierarchical summary: processing %d chunks in tree", len(chunks))

    # L1: Summarize each chunk
    semaphore = asyncio.Semaphore(config.max_concurrent_chunks)

    async def summarize_with_limit(idx: int, chunk: str) -> ChunkSummary:
        async with semaphore:
            # Assign to L2 group (L2_GROUP_SIZE chunks per group)
            group_idx = idx // L2_GROUP_SIZE
            return await _summarize_single_chunk(
                chunk,
                idx,
                len(chunks),
                config,
                parent_group=group_idx,
            )

    l1_summaries = await asyncio.gather(
        *[summarize_with_limit(i, chunk) for i, chunk in enumerate(chunks)],
    )

    # L2: Group summaries (if more than L2_MIN_CHUNKS chunks)
    l2_summaries: list[str] = []
    if len(l1_summaries) > L2_MIN_CHUNKS:
        groups: list[list[str]] = []
        for i in range(0, len(l1_summaries), L2_GROUP_SIZE):
            group = [cs.content for cs in l1_summaries[i : i + L2_GROUP_SIZE]]
            groups.append(group)

        async def summarize_group(group: list[str]) -> str:
            combined_tokens = sum(count_tokens(s, config.model) for s in group)
            target_tokens = estimate_summary_tokens(combined_tokens, SummaryLevel.STANDARD)
            max_words = tokens_to_words(target_tokens)

            prompt = META_SUMMARY_PROMPT.format(
                summaries=format_summaries_for_meta(group),
                max_words=max_words,
            )
            return await _generate_summary(prompt, config, max_tokens=target_tokens + 50)

        l2_summaries = await asyncio.gather(*[summarize_group(g) for g in groups])

    # L3: Final synthesis
    summaries_to_synthesize = l2_summaries if l2_summaries else [cs.content for cs in l1_summaries]
    final_target = estimate_summary_tokens(input_tokens, SummaryLevel.HIERARCHICAL)
    max_words = tokens_to_words(final_target)

    final_prompt = META_SUMMARY_PROMPT.format(
        summaries=format_summaries_for_meta(summaries_to_synthesize),
        max_words=max_words,
    )

    final_summary = await _generate_summary(
        final_prompt,
        config,
        max_tokens=final_target + 100,
    )
    output_tokens = count_tokens(final_summary, config.model)

    hierarchical = HierarchicalSummary(
        l1_summaries=list(l1_summaries),
        l2_summaries=list(l2_summaries),
        l3_summary=final_summary,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )

    return SummaryResult(
        level=SummaryLevel.HIERARCHICAL,
        summary=final_summary,
        hierarchical=hierarchical,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        compression_ratio=output_tokens / input_tokens if input_tokens > 0 else 0.0,
    )


async def _generate_summary(
    prompt: str,
    config: SummarizerConfig,
    max_tokens: int = 256,
    *,
    attempt: int = 0,
) -> str:
    """Generate a summary using the LLM.

    Uses PydanticAI for structured output with fallback to raw generation.
    Implements exponential backoff retry on failures.

    Args:
        prompt: The prompt to send to the LLM.
        config: Summarizer configuration.
        max_tokens: Maximum tokens for the response.
        attempt: Current retry attempt (for internal recursion).

    Returns:
        The generated summary text.

    Raises:
        SummarizationError: If all retries are exhausted.

    """
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
        logger.warning("Structured summary failed, trying raw generation: %s", e)
        # Fallback to raw HTTP call
        try:
            return await _raw_generate(prompt, config, max_tokens)
        except Exception as raw_err:
            if attempt < MAX_SUMMARIZE_RETRIES:
                wait_time = 2**attempt  # Exponential backoff: 1, 2, 4 seconds
                logger.warning(
                    "Raw generation failed (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1,
                    MAX_SUMMARIZE_RETRIES,
                    wait_time,
                    raw_err,
                )
                await asyncio.sleep(wait_time)
                return await _generate_summary(
                    prompt,
                    config,
                    max_tokens,
                    attempt=attempt + 1,
                )
            msg = f"Summarization failed after {MAX_SUMMARIZE_RETRIES} retries"
            raise SummarizationError(msg) from raw_err


async def _raw_generate(prompt: str, config: SummarizerConfig, max_tokens: int) -> str:
    """Fallback raw HTTP generation without structured output."""
    async with httpx.AsyncClient(timeout=config.timeout) as client:
        response = await client.post(
            f"{config.openai_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {config.api_key}"},
            json={
                "model": config.model,
                "messages": [
                    {"role": "system", "content": "You are a concise summarizer."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "").strip()
    return ""
