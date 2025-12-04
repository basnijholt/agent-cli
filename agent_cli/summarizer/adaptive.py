"""Adaptive summarization using map-reduce with dynamic collapse.

Implements a simple algorithm inspired by LangChain's map-reduce chains:
1. If content fits target, return as-is (no LLM call)
2. Otherwise, split into chunks and summarize each (map phase)
3. Recursively collapse summaries until they fit target (reduce phase)

Research foundations:
- LangChain ReduceDocumentsChain: token_max=3000, recursive collapse
- BOOOOKSCORE (arXiv:2310.00785): chunk_size=2048 optimal

See docs/architecture/summarizer.md for detailed design rationale.
"""

from __future__ import annotations

import logging

from agent_cli.summarizer._prompts import (
    format_prior_context,
    get_prompt_for_content_type,
)
from agent_cli.summarizer._utils import (
    count_tokens,
    generate_summary,
    tokens_to_words,
)
from agent_cli.summarizer.map_reduce import map_reduce_summarize
from agent_cli.summarizer.models import (
    SummarizerConfig,
    SummaryResult,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SummarizerConfig",
    "summarize",
]


async def summarize(
    content: str,
    config: SummarizerConfig,
    *,
    target_tokens: int | None = None,
    target_ratio: float | None = None,
    prior_summary: str | None = None,
    content_type: str = "general",
) -> SummaryResult:
    """Summarize content to fit within a target token limit.

    Simple algorithm:
    - If content already fits target, return as-is (no LLM call)
    - Otherwise, use map-reduce to compress until it fits

    Args:
        content: The content to summarize.
        config: Summarizer configuration.
        target_tokens: Absolute token limit (e.g., 4000). Defaults to config.token_max.
        target_ratio: Relative compression ratio (e.g., 0.2 = compress to 20% of input).
            Takes precedence over target_tokens if both provided.
        prior_summary: Optional prior summary for context continuity.
        content_type: Type of content ("general", "conversation", "journal", "document").

    Returns:
        SummaryResult with summary and compression metrics.

    Examples:
        # Compress to fit 4000 tokens
        result = await summarize(huge_doc, config, target_tokens=4000)

        # Compress to 20% of original size
        result = await summarize(huge_doc, config, target_ratio=0.2)

        # Use default (config.token_max = 3000)
        result = await summarize(huge_doc, config)

    """
    if not content or not content.strip():
        return SummaryResult(
            summary=None,
            input_tokens=0,
            output_tokens=0,
            compression_ratio=0.0,
        )

    input_tokens = count_tokens(content, config.model)

    # Determine target
    if target_ratio is not None:
        target = max(1, int(input_tokens * target_ratio))
    elif target_tokens is not None:
        target = target_tokens
    else:
        target = config.token_max

    logger.info(
        "Summarizing %d tokens to target %d (type=%s)",
        input_tokens,
        target,
        content_type,
    )

    # Already fits? Return content as-is (no LLM call)
    if input_tokens <= target:
        return SummaryResult(
            summary=content,
            input_tokens=input_tokens,
            output_tokens=input_tokens,
            compression_ratio=1.0,
            collapse_depth=0,
        )

    # Content fits in single chunk but exceeds target - use content-aware summary
    if input_tokens <= config.chunk_size:
        summary = await _content_aware_summary(
            content,
            config,
            target,
            prior_summary,
            content_type,
        )
        output_tokens = count_tokens(summary, config.model)
        return SummaryResult(
            summary=summary,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            compression_ratio=output_tokens / input_tokens,
            collapse_depth=0,
        )

    # Large content - use map-reduce with dynamic collapse
    result = await map_reduce_summarize(content, config, target)

    return SummaryResult(
        summary=result.summary,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        compression_ratio=result.compression_ratio,
        collapse_depth=result.collapse_depth,
    )


async def _content_aware_summary(
    content: str,
    config: SummarizerConfig,
    target_tokens: int,
    prior_summary: str | None,
    content_type: str,
) -> str:
    """Generate a content-type aware summary for single-chunk content."""
    max_words = tokens_to_words(target_tokens)

    prompt_template = get_prompt_for_content_type(content_type)
    prior_context = format_prior_context(prior_summary)

    prompt = prompt_template.format(
        content=content,
        prior_context=prior_context,
        max_words=max_words,
    )

    return await generate_summary(prompt, config, max_tokens=target_tokens + 50)
