"""Adaptive summarization module for variable-length content.

This module provides map-reduce summarization inspired by LangChain's approach:
1. If content fits target, return as-is (no LLM call)
2. Otherwise, split into chunks and summarize each in parallel (map phase)
3. Recursively collapse summaries until they fit target (reduce phase)

Research foundations:
- LangChain ReduceDocumentsChain: token_max=3000, recursive collapse
- BOOOOKSCORE (arXiv:2310.00785): chunk_size=2048 optimal

Example:
    from agent_cli.summarizer import summarize, SummarizerConfig

    config = SummarizerConfig(
        openai_base_url="http://localhost:8000/v1",
        model="gpt-4",
    )

    # Compress to fit 4000 tokens
    result = await summarize(long_document, config, target_tokens=4000)

    # Compress to 20% of original size
    result = await summarize(long_document, config, target_ratio=0.2)

    print(f"Compression: {result.compression_ratio:.1%}")

"""

from agent_cli.summarizer.adaptive import summarize
from agent_cli.summarizer.models import (
    SummarizationError,
    SummarizerConfig,
    SummaryResult,
)

__all__ = [
    "SummarizationError",
    "SummarizerConfig",
    "SummaryResult",
    "summarize",
]
