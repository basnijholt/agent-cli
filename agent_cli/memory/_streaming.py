"""Streaming helpers for chat completions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from agent_cli.core.sse import extract_content_from_chunk, parse_chunk

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@dataclass
class StreamingAccumulator:
    """Accumulator for streaming response text and metadata."""

    text_chunks: list[str] = field(default_factory=list)
    model: str | None = None
    system_fingerprint: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    # Timing metadata (llama.cpp style)
    prompt_ms: float | None = None
    predicted_ms: float | None = None
    prompt_per_second: float | None = None
    predicted_per_second: float | None = None
    cache_tokens: int | None = None

    def get_text(self) -> str | None:
        """Return accumulated text or None if empty."""
        text = "".join(self.text_chunks).strip()
        return text or None


async def stream_chat_sse(
    *,
    openai_base_url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    request_timeout: float = 120.0,
) -> AsyncGenerator[str, None]:
    """Stream Server-Sent Events from an OpenAI-compatible chat completion endpoint."""
    url = f"{openai_base_url.rstrip('/')}/chat/completions"
    async with (
        httpx.AsyncClient(timeout=request_timeout) as client,
        client.stream("POST", url, json=payload, headers=headers) as response,
    ):
        if response.status_code != 200:  # noqa: PLR2004
            error_text = await response.aread()
            yield f"data: {error_text.decode(errors='ignore')}\n\n"
            return
        async for line in response.aiter_lines():
            if line:
                yield line


def accumulate_assistant_text(line: str, buffer: list[str]) -> None:
    """Parse SSE line and append any assistant text delta into buffer."""
    chunk = parse_chunk(line)
    if chunk is None:
        return
    piece = extract_content_from_chunk(chunk)
    if piece:
        buffer.append(piece)


def accumulate_streaming_data(line: str, accumulator: StreamingAccumulator) -> None:
    """Parse SSE line and accumulate text and metadata into accumulator."""
    chunk = parse_chunk(line)
    if chunk is None:
        return

    # Accumulate text content
    piece = extract_content_from_chunk(chunk)
    if piece:
        accumulator.text_chunks.append(piece)

    # Capture model from first chunk
    if chunk.get("model") and not accumulator.model:
        accumulator.model = chunk["model"]

    # Capture system fingerprint
    if chunk.get("system_fingerprint") and not accumulator.system_fingerprint:
        accumulator.system_fingerprint = chunk["system_fingerprint"]

    # Capture usage data (usually in final chunk)
    if chunk.get("usage"):
        usage = chunk["usage"]
        accumulator.prompt_tokens = usage.get("prompt_tokens")
        accumulator.completion_tokens = usage.get("completion_tokens")
        accumulator.total_tokens = usage.get("total_tokens")

    # Capture timing data (llama.cpp style, usually in final chunk)
    if chunk.get("timings"):
        timings = chunk["timings"]
        accumulator.prompt_ms = timings.get("prompt_ms")
        accumulator.predicted_ms = timings.get("predicted_ms")
        accumulator.prompt_per_second = timings.get("prompt_per_second")
        accumulator.predicted_per_second = timings.get("predicted_per_second")
        accumulator.cache_tokens = timings.get("cache_n")
