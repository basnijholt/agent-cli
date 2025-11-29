"""Adaptive summarization module for variable-length content.

This module provides map-reduce summarization inspired by LangChain's approach:
1. Split content into chunks and summarize each in parallel (map phase)
2. Recursively collapse summaries until they fit token_max (reduce phase)

Research foundations:
- LangChain ReduceDocumentsChain: token_max=3000, recursive collapse
- BOOOOKSCORE (arXiv:2310.00785): chunk_size=2048 optimal
- Two-phase architecture concept from Mem0 (arXiv:2504.19413)

Example:
    from agent_cli.summarizer import summarize, SummarizerConfig

    config = SummarizerConfig(
        openai_base_url="http://localhost:8000/v1",
        model="gpt-4",
    )
    result = await summarize(long_document, config)
    print(f"Level: {result.level.name}, Compression: {result.compression_ratio:.1%}")

"""

from agent_cli.summarizer.adaptive import summarize
from agent_cli.summarizer.models import (
    SummarizationError,
    SummarizerConfig,
    SummaryLevel,
    SummaryResult,
)

__all__ = [
    "SummarizationError",
    "SummarizerConfig",
    "SummaryLevel",
    "SummaryResult",
    "summarize",
]
