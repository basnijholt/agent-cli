"""Shared OpenAI-compatible forwarding helpers."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable

logger = logging.getLogger("agent_cli.core.openai_proxy")


@runtime_checkable
class ChatRequestLike(Protocol):
    """Minimal interface required to forward a chat request."""

    stream: bool | None

    def model_dump(self, *, exclude: set[str] | None = None) -> dict[str, Any]:
        """Serialize request to a dict for forwarding."""


async def forward_chat_request(
    request: ChatRequestLike,
    openai_base_url: str,
    api_key: str | None = None,
    *,
    exclude_fields: Iterable[str] = (),
) -> Any:
    """Forward a chat request to a backend LLM."""
    forward_payload = request.model_dump(exclude=set(exclude_fields))
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None

    if getattr(request, "stream", False):

        async def generate() -> AsyncGenerator[str, None]:
            try:
                async with (
                    httpx.AsyncClient(timeout=120.0) as client,
                    client.stream(
                        "POST",
                        f"{openai_base_url.rstrip('/')}/chat/completions",
                        json=forward_payload,
                        headers=headers,
                    ) as response,
                ):
                    if response.status_code != 200:  # noqa: PLR2004
                        error_text = await response.aread()
                        yield f"data: {json.dumps({'error': str(error_text)})}\n\n"
                        return

                    async for chunk in response.aiter_raw():
                        if isinstance(chunk, bytes):
                            yield chunk.decode("utf-8")
                        else:
                            yield chunk
            except Exception as exc:
                logger.exception("Streaming error")
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{openai_base_url.rstrip('/')}/chat/completions",
            json=forward_payload,
            headers=headers,
        )
        if response.status_code != 200:  # noqa: PLR2004
            logger.error(
                "Upstream error %s: %s",
                response.status_code,
                response.text,
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Upstream error: {response.text}",
            )

        return response.json()
