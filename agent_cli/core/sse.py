"""Shared SSE (Server-Sent Events) formatting helpers for OpenAI-compatible streaming."""

from __future__ import annotations

import json
import time
from typing import Any


def format_chunk(
    run_id: str,
    model: str,
    *,
    content: str | None = None,
    finish_reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Format a single SSE chunk in OpenAI chat.completion.chunk format.

    Args:
        run_id: Unique identifier for this completion.
        model: Model name to include in response.
        content: Text content delta (None for finish chunk).
        finish_reason: Reason for completion (e.g., "stop").
        extra: Additional fields to include in the response.

    Returns:
        Formatted SSE data line.

    """
    data: dict[str, Any] = {
        "id": f"chatcmpl-{run_id}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            },
        ],
    }
    if extra:
        data.update(extra)
    return f"data: {json.dumps(data)}\n\n"


def format_done() -> str:
    """Format the terminal [DONE] SSE message."""
    return "data: [DONE]\n\n"


def parse_chunk(line: str) -> dict[str, Any] | None:
    """Parse an SSE data line into a dict.

    Args:
        line: Raw SSE line (e.g., "data: {...}").

    Returns:
        Parsed JSON dict, or None if not parseable or [DONE].

    """
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if payload == "[DONE]":
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def extract_content_from_chunk(chunk: dict[str, Any]) -> str:
    """Extract text content from a parsed SSE chunk.

    Args:
        chunk: Parsed chunk dict from parse_chunk().

    Returns:
        Content string, or empty string if not found.

    """
    choices = chunk.get("choices") or [{}]
    delta = choices[0].get("delta") or {}
    return delta.get("content") or delta.get("text") or ""
