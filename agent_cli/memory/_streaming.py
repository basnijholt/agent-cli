"""Streaming helpers for chat completions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_cli.core.sse import extract_content_from_chunk, parse_chunk

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


async def stream_chat_sse(
    *,
    openai_base_url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    request_timeout: float = 120.0,
) -> AsyncGenerator[str, None]:
    """Stream Server-Sent Events from an OpenAI-compatible chat completion endpoint."""
    import httpx  # noqa: PLC0415

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
