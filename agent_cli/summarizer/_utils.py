"""Utility functions for adaptive summarization."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

from agent_cli.summarizer.models import SummaryLevel

if TYPE_CHECKING:
    import tiktoken


@lru_cache(maxsize=4)
def _get_encoding(model: str = "gpt-4") -> tiktoken.Encoding:
    """Get tiktoken encoding for a model, with caching.

    Falls back to cl100k_base for unknown models (covers most modern LLMs).
    """
    import tiktoken  # noqa: PLC0415

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens in text using tiktoken.

    Args:
        text: The text to count tokens for.
        model: Model name for tokenizer selection.

    Returns:
        Number of tokens in the text.

    """
    if not text:
        return 0
    enc = _get_encoding(model)
    # Disable special token checking - LLM outputs may contain special tokens
    # like <|constrain|>, <|endoftext|>, etc. that we want to count normally
    return len(enc.encode(text, disallowed_special=()))


def chunk_text(
    text: str,
    chunk_size: int = 3000,
    overlap: int = 200,
    model: str = "gpt-4",
) -> list[str]:
    """Split text into overlapping chunks by token count.

    Uses semantic boundaries (paragraphs, sentences) when possible to avoid
    splitting mid-thought. Falls back to token-based splitting if no good
    boundaries are found.

    Args:
        text: The text to chunk.
        chunk_size: Target token count per chunk.
        overlap: Token overlap between chunks for context continuity.
        model: Model name for tokenizer.

    Returns:
        List of text chunks.

    """
    if not text:
        return []

    total_tokens = count_tokens(text, model)
    if total_tokens <= chunk_size:
        return [text]

    # Split into paragraphs first
    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return [text]

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = count_tokens(para, model)

        # If single paragraph exceeds chunk size, split it further
        if para_tokens > chunk_size:
            # Flush current chunk if any
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_tokens = 0

            # Split large paragraph by sentences
            sentences = _split_sentences(para)
            for sentence in sentences:
                sent_tokens = count_tokens(sentence, model)
                if current_tokens + sent_tokens > chunk_size and current_chunk:
                    chunks.append(" ".join(current_chunk))
                    # Keep overlap from end of previous chunk
                    overlap_text = _get_overlap_text(current_chunk, overlap, model)
                    current_chunk = [overlap_text] if overlap_text else []
                    current_tokens = count_tokens(overlap_text, model) if overlap_text else 0
                current_chunk.append(sentence)
                current_tokens += sent_tokens
        elif current_tokens + para_tokens > chunk_size:
            # Flush current chunk and start new one
            chunks.append("\n\n".join(current_chunk))
            # Keep overlap from end of previous chunk
            overlap_text = _get_overlap_text(current_chunk, overlap, model)
            current_chunk = [overlap_text, para] if overlap_text else [para]
            current_tokens = (
                count_tokens(overlap_text, model) + para_tokens if overlap_text else para_tokens
            )
        else:
            current_chunk.append(para)
            current_tokens += para_tokens

    # Don't forget the last chunk
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving common abbreviations."""
    # Simple sentence splitting that handles common cases
    # Matches period/question/exclamation followed by space and capital letter
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [s.strip() for s in sentences if s.strip()]


def _get_overlap_text(chunks: list[str], target_tokens: int, model: str) -> str:
    """Extract overlap text from end of chunk list.

    Takes text from the end of the chunk list until reaching target_tokens.
    """
    if not chunks or target_tokens <= 0:
        return ""

    # Work backwards through chunks
    overlap_parts: list[str] = []
    tokens_collected = 0

    for chunk in reversed(chunks):
        chunk_tokens = count_tokens(chunk, model)
        if tokens_collected + chunk_tokens <= target_tokens:
            overlap_parts.insert(0, chunk)
            tokens_collected += chunk_tokens
        else:
            # Take partial chunk if needed
            words = chunk.split()
            partial: list[str] = []
            for word in reversed(words):
                word_tokens = count_tokens(word, model)
                if tokens_collected + word_tokens <= target_tokens:
                    partial.insert(0, word)
                    tokens_collected += word_tokens
                else:
                    break
            if partial:
                overlap_parts.insert(0, " ".join(partial))
            break

    return " ".join(overlap_parts)


def middle_truncate(
    text: str,
    budget_chars: int,
    head_frac: float = 0.3,
    tail_frac: float = 0.3,
) -> tuple[str, int]:
    """Middle-truncate text to fit within a character budget.

    Keeps the first head_frac and last tail_frac portions, dropping the middle.
    This preserves context from both the beginning (often contains setup) and
    end (often contains conclusions/recent events).

    Inspired by Letta's `middle_truncate_text` function.

    Args:
        text: Text to truncate.
        budget_chars: Maximum character count for output.
        head_frac: Fraction of budget for the head portion.
        tail_frac: Fraction of budget for the tail portion.

    Returns:
        Tuple of (truncated_text, dropped_char_count).

    """
    if budget_chars <= 0 or len(text) <= budget_chars:
        return text, 0

    head_len = max(0, int(budget_chars * head_frac))
    tail_len = max(0, int(budget_chars * tail_frac))

    # Ensure head + tail doesn't exceed budget
    if head_len + tail_len > budget_chars:
        tail_len = max(0, budget_chars - head_len)

    head = text[:head_len]
    tail = text[-tail_len:] if tail_len > 0 else ""
    dropped = max(0, len(text) - (len(head) + len(tail)))

    marker = f"\n[...{dropped} characters truncated...]\n"

    # If marker would overflow budget, shrink tail
    available_for_marker = budget_chars - (len(head) + len(tail))
    if available_for_marker < len(marker):
        over = len(marker) - available_for_marker
        tail = tail[:-over] if over < len(tail) else ""

    return head + marker + tail, dropped


def estimate_summary_tokens(input_tokens: int, level: int) -> int:
    """Estimate target summary tokens based on input size and level.

    Compression ratios based on Mem0 research:
    - BRIEF: ~20% compression (80% reduction)
    - STANDARD: ~12% compression (88% reduction)
    - DETAILED: ~7% compression (93% reduction)
    - HIERARCHICAL: Capped with diminishing returns

    Args:
        input_tokens: Number of tokens in the input.
        level: Summary level (1-4).

    Returns:
        Target number of tokens for the summary.

    """
    if level == SummaryLevel.NONE:
        return 0
    if level == SummaryLevel.BRIEF:
        return min(50, max(20, input_tokens // 5))
    if level == SummaryLevel.STANDARD:
        return min(200, max(50, input_tokens // 8))
    if level == SummaryLevel.DETAILED:
        return min(500, max(100, input_tokens // 15))
    # HIERARCHICAL
    # Base of 1000 tokens plus diminishing returns for additional content
    base = 1000
    additional = max(0, (input_tokens - 15000) // 100)
    return min(2000, base + additional)


def tokens_to_words(tokens: int) -> int:
    """Convert token count to approximate word count.

    Rough approximation: 1 token ≈ 0.75 words for English text.
    """
    return int(tokens * 0.75)
