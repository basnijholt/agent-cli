"""Utility functions for adaptive summarization."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic import BaseModel

from agent_cli.summarizer.models import SummarizationError, SummarizerConfig

if TYPE_CHECKING:
    import tiktoken


class SummaryOutput(BaseModel):
    """Structured output for summary generation."""

    summary: str


async def generate_summary(
    prompt: str,
    config: SummarizerConfig,
    max_tokens: int = 256,
) -> str:
    """Call the LLM to generate a summary.

    Args:
        prompt: The prompt to send to the LLM.
        config: Summarizer configuration.
        max_tokens: Maximum tokens for the response.

    Returns:
        The generated summary text.

    Raises:
        SummarizationError: If the LLM call fails.

    """
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


@lru_cache(maxsize=4)
def _get_encoding(model: str = "gpt-4") -> tiktoken.Encoding | None:
    """Get tiktoken encoding for a model, with caching.

    Falls back to cl100k_base for unknown models (covers most modern LLMs).
    Returns None when tiktoken is not installed so callers can use a heuristic.
    """
    try:
        import tiktoken  # noqa: PLC0415
    except ModuleNotFoundError:
        return None

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens using tiktoken, falling back to char-based estimate."""
    if not text:
        return 0
    enc = _get_encoding(model)
    if enc is None:
        return _estimate_token_count(text)
    # Disable special token checking - LLM outputs may contain special tokens
    # like <|constrain|>, <|endoftext|>, etc. that we want to count normally
    return len(enc.encode(text, disallowed_special=()))


def _estimate_token_count(text: str) -> int:
    """Very rough token estimate based on character length (~4 chars/token)."""
    return max(1, (len(text) + 3) // 4)


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


def estimate_summary_tokens(input_tokens: int) -> int:
    """Estimate target summary tokens based on input size.

    Uses ~10% compression ratio with floor/ceiling bounds.
    """
    return min(500, max(50, input_tokens // 10))


def tokens_to_words(tokens: int) -> int:
    """Convert token count to approximate word count.

    Rough approximation: 1 token ≈ 0.75 words for English text.
    """
    return int(tokens * 0.75)
