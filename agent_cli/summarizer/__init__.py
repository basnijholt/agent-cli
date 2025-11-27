"""Adaptive summarization module for variable-length content.

This module provides research-grounded summarization that scales with input complexity,
inspired by Letta (partial eviction, middle truncation) and Mem0 (rolling summaries,
compression ratios) architectures.

Example:
    from agent_cli.summarizer import AdaptiveSummarizer, SummaryLevel

    summarizer = AdaptiveSummarizer(
        openai_base_url="http://localhost:8000/v1",
        model="gpt-4",
    )
    result = await summarizer.summarize(long_document)
    print(f"Level: {result.level}, Compression: {result.compression_ratio:.1%}")

"""

from agent_cli.summarizer.adaptive import AdaptiveSummarizer
from agent_cli.summarizer.models import (
    HierarchicalSummary,
    SummaryLevel,
    SummaryResult,
)

__all__ = [
    "AdaptiveSummarizer",
    "HierarchicalSummary",
    "SummaryLevel",
    "SummaryResult",
]
