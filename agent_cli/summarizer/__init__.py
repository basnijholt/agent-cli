"""Adaptive summarization module for variable-length content.

This module provides research-grounded summarization that scales with input complexity,
inspired by Letta (partial eviction, middle truncation) and Mem0 (rolling summaries,
compression ratios) architectures.

Example:
    from agent_cli.summarizer import summarize, SummarizerConfig

    config = SummarizerConfig(
        openai_base_url="http://localhost:8000/v1",
        model="gpt-4",
    )
    result = await summarize(long_document, config)
    print(f"Level: {result.level.name}, Compression: {result.compression_ratio:.1%}")

"""

from agent_cli.summarizer.adaptive import SummarizationError, SummarizerConfig, summarize
from agent_cli.summarizer.models import HierarchicalSummary, SummaryLevel, SummaryResult

__all__ = [
    "HierarchicalSummary",
    "SummarizationError",
    "SummarizerConfig",
    "SummaryLevel",
    "SummaryResult",
    "summarize",
]
