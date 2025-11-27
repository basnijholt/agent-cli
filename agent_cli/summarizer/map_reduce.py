"""Map-reduce summarization inspired by LangChain's approach.

Simple algorithm:
1. Map: Split content into chunks, summarize each in parallel
2. Reduce: If combined summaries exceed token_max, recursively collapse

Key insight from LangChain: No need for predetermined levels (L1/L2/L3).
Just keep collapsing until content fits. Dynamic depth based on actual content.

References:
- LangChain ReduceDocumentsChain: token_max=3000, recursive collapse
- BOOOOKSCORE: chunk_size=2048 optimal for summarization

"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from agent_cli.summarizer._prompts import (
    CHUNK_SUMMARY_PROMPT,
    META_SUMMARY_PROMPT,
    format_summaries_for_meta,
)
from agent_cli.summarizer._utils import (
    SummarizationError,
    SummarizerConfig,
    chunk_text,
    count_tokens,
    estimate_summary_tokens,
    generate_summary,
    tokens_to_words,
)
from agent_cli.summarizer.models import SummaryLevel

logger = logging.getLogger(__name__)


class MapReduceSummarizationError(SummarizationError):
    """Raised when map-reduce summarization fails."""


@dataclass
class MapReduceResult:
    """Result of map-reduce summarization.

    Attributes:
        summary: The final collapsed summary.
        input_tokens: Token count of original content.
        output_tokens: Token count of final summary.
        compression_ratio: output_tokens / input_tokens.
        collapse_depth: How many reduce iterations were needed.
        intermediate_summaries: All intermediate summaries (for debugging/storage).

    """

    summary: str
    input_tokens: int
    output_tokens: int
    compression_ratio: float
    collapse_depth: int
    intermediate_summaries: list[list[str]]  # Each level of collapse


async def map_reduce_summarize(
    content: str,
    config: SummarizerConfig,
    max_collapse_depth: int = 10,
) -> MapReduceResult:
    """Summarize content using map-reduce with dynamic collapse.

    Algorithm:
    1. Split into chunks and summarize each (map phase)
    2. If combined summaries exceed token_max, recursively collapse (reduce phase)
    3. Continue until everything fits in token_max

    Note: This function is designed for content that exceeds token_max. For shorter
    content, use the main `summarize()` function in adaptive.py which selects the
    appropriate strategy (NONE, BRIEF, or MAP_REDUCE with content-aware prompts).

    Args:
        content: The content to summarize.
        config: Summarizer configuration.
        max_collapse_depth: Safety limit on recursive collapse depth.

    Returns:
        MapReduceResult with summary and metadata.

    """
    input_tokens = count_tokens(content, config.model)

    # Map phase: Split and summarize chunks in parallel
    chunks = chunk_text(
        content,
        chunk_size=config.chunk_size,
        overlap=config.chunk_overlap,
        model=config.model,
    )

    logger.info("Map phase: processing %d chunks", len(chunks))
    summaries = await _map_summarize(chunks, config)
    intermediate_summaries = [summaries.copy()]

    # Reduce phase: Recursively collapse until fits token_max
    depth = 0
    while _total_tokens(summaries, config.model) > config.token_max:
        depth += 1
        if depth > max_collapse_depth:
            logger.warning(
                "Hit max collapse depth %d, forcing final summary",
                max_collapse_depth,
            )
            break

        logger.info(
            "Reduce phase (depth %d): collapsing %d summaries (%d tokens)",
            depth,
            len(summaries),
            _total_tokens(summaries, config.model),
        )
        summaries = await _collapse_summaries(summaries, config)
        intermediate_summaries.append(summaries.copy())

    # Final synthesis if we have multiple summaries left
    if len(summaries) > 1:
        final_summary = await _synthesize(summaries, config)
    else:
        final_summary = summaries[0]

    output_tokens = count_tokens(final_summary, config.model)

    return MapReduceResult(
        summary=final_summary,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        compression_ratio=output_tokens / input_tokens,
        collapse_depth=depth,
        intermediate_summaries=intermediate_summaries,
    )


def _total_tokens(texts: list[str], model: str) -> int:
    """Count total tokens across all texts."""
    return sum(count_tokens(t, model) for t in texts)


async def _map_summarize(chunks: list[str], config: SummarizerConfig) -> list[str]:
    """Summarize each chunk in parallel (map phase)."""
    semaphore = asyncio.Semaphore(config.max_concurrent_chunks)
    total = len(chunks)

    async def summarize_chunk(idx: int, chunk: str) -> str:
        async with semaphore:
            return await _summarize_chunk(chunk, idx, total, config)

    tasks = [summarize_chunk(i, chunk) for i, chunk in enumerate(chunks)]
    return list(await asyncio.gather(*tasks))


async def _summarize_chunk(
    chunk: str,
    chunk_index: int,
    total_chunks: int,
    config: SummarizerConfig,
) -> str:
    """Summarize a single chunk."""
    source_tokens = count_tokens(chunk, config.model)
    target_tokens = estimate_summary_tokens(source_tokens, SummaryLevel.MAP_REDUCE)
    max_words = tokens_to_words(target_tokens)

    prompt = CHUNK_SUMMARY_PROMPT.format(
        chunk_index=chunk_index + 1,
        total_chunks=total_chunks,
        content=chunk,
        max_words=max_words,
    )

    return await generate_summary(prompt, config, max_tokens=target_tokens + 50)


async def _collapse_summaries(
    summaries: list[str],
    config: SummarizerConfig,
) -> list[str]:
    """Collapse summaries by grouping and re-summarizing (reduce phase).

    Groups summaries that together fit within token_max, then summarizes each group.
    This is similar to LangChain's split_list_of_docs approach.
    """
    if len(summaries) <= 1:
        return summaries

    # Group summaries that together fit within token_max
    groups: list[list[str]] = []
    current_group: list[str] = []
    current_tokens = 0

    for summary in summaries:
        summary_tokens = count_tokens(summary, config.model)

        # If adding this summary would exceed token_max, start new group
        if current_tokens + summary_tokens > config.token_max and current_group:
            groups.append(current_group)
            current_group = [summary]
            current_tokens = summary_tokens
        else:
            current_group.append(summary)
            current_tokens += summary_tokens

    if current_group:
        groups.append(current_group)

    # Summarize each group in parallel
    semaphore = asyncio.Semaphore(config.max_concurrent_chunks)

    async def summarize_group(group: list[str]) -> str:
        async with semaphore:
            return await _synthesize(group, config)

    tasks = [summarize_group(g) for g in groups]
    return list(await asyncio.gather(*tasks))


async def _synthesize(summaries: list[str], config: SummarizerConfig) -> str:
    """Synthesize multiple summaries into one."""
    combined_tokens = sum(count_tokens(s, config.model) for s in summaries)
    target_tokens = estimate_summary_tokens(combined_tokens, SummaryLevel.MAP_REDUCE)
    max_words = tokens_to_words(target_tokens)

    prompt = META_SUMMARY_PROMPT.format(
        summaries=format_summaries_for_meta(summaries),
        max_words=max_words,
    )

    return await generate_summary(prompt, config, max_tokens=target_tokens + 100)
