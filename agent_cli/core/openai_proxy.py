"""Shared OpenAI-compatible forwarding helpers."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable

    from fastapi import Request, Response

LOGGER = logging.getLogger(__name__)


@runtime_checkable
class ChatRequestLike(Protocol):
    """Minimal interface required to forward a chat request."""

    stream: bool | None

    def model_dump(self, *, exclude: set[str] | None = None) -> dict[str, Any]:
        """Serialize request to a dict for forwarding."""


async def proxy_request_to_upstream(
    request: Request,
    path: str,
    upstream_base_url: str,
    api_key: str | None = None,
) -> Response:
    """Forward a raw HTTP request to an upstream OpenAI-compatible provider."""
    import httpx  # noqa: PLC0415
    from fastapi import Response  # noqa: PLC0415

    auth_header = request.headers.get("Authorization")
    headers = {}
    if auth_header:
        headers["Authorization"] = auth_header
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    if request.headers.get("Content-Type"):
        headers["Content-Type"] = request.headers.get("Content-Type")

    base = upstream_base_url.rstrip("/")
    target_path = path

    # Smart path joining to avoid /v1/v1/ if base already has it
    if base.endswith("/v1") and (path == "v1" or path.startswith("v1/")):
        target_path = path[2:].lstrip("/")

    url = f"{base}/{target_path}"

    try:
        body = await request.body()
        async with httpx.AsyncClient(timeout=60.0) as http:
            req = http.build_request(
                request.method,
                url,
                headers=headers,
                content=body,
                params=request.query_params,
            )
            resp = await http.send(req)

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("Content-Type"),
            )
    except Exception:
        LOGGER.warning("Proxy request failed to %s", url, exc_info=True)
        return Response(status_code=502, content="Upstream Proxy Error")


async def forward_chat_request(
    request: ChatRequestLike,
    openai_base_url: str,
    api_key: str | None = None,
    *,
    exclude_fields: Iterable[str] = (),
) -> Any:
    """Forward a chat request to a backend LLM."""
    import httpx  # noqa: PLC0415
    from fastapi import HTTPException  # noqa: PLC0415
    from fastapi.responses import StreamingResponse  # noqa: PLC0415

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
                LOGGER.exception("Streaming error")
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{openai_base_url.rstrip('/')}/chat/completions",
            json=forward_payload,
            headers=headers,
        )
        if response.status_code != 200:  # noqa: PLR2004
            LOGGER.error(
                "Upstream error %s: %s",
                response.status_code,
                response.text,
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Upstream error: {response.text}",
            )

        return response.json()
