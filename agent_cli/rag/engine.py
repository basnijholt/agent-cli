"""Core RAG Engine Logic (Functional)."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from agent_cli.rag.models import Message
from agent_cli.rag.retriever import search_context

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from chromadb import Collection
    from sentence_transformers import CrossEncoder

    from agent_cli.rag.models import ChatRequest, RetrievalResult

logger = logging.getLogger("agent_cli.rag.engine")


def augment_chat_request(
    request: ChatRequest,
    collection: Collection,
    reranker_model: CrossEncoder,
    default_top_k: int = 3,
) -> tuple[ChatRequest, RetrievalResult | None]:
    """Retrieve context and augment the chat request.

    Returns:
        A tuple of (augmented_request, retrieval_result).
        If no retrieval happened or no context was found, retrieval_result is None.

    """
    # Get last user message
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        None,
    )

    if not user_message:
        return request, None

    # Retrieve
    retrieval = search_context(
        collection,
        reranker_model,
        user_message,
        top_k=request.rag_top_k or default_top_k,
    )

    if not retrieval.context:
        logger.info("ℹ️  No relevant context found for query: '%s'", user_message[:50])  # noqa: RUF001
        return request, None

    logger.info(
        "✅ Found %d relevant sources for query: '%s'",
        len(retrieval.sources),
        user_message[:50],
    )

    # Augment prompt
    augmented_content = (
        f"Context from documentation:\n{retrieval.context}\n\n---\n\nQuestion: {user_message}"
    )

    # Create new messages list
    augmented_messages = list(request.messages[:-1])
    # Add augmented user message
    augmented_messages.append(Message(role="user", content=augmented_content))

    # Create augmented request
    aug_request = request.model_copy()
    aug_request.messages = augmented_messages

    return aug_request, retrieval


async def process_chat_request(
    request: ChatRequest,
    collection: Collection,
    reranker_model: CrossEncoder,
    openai_base_url: str,
    default_top_k: int = 3,
) -> Any:
    """Process a chat request with RAG."""
    aug_request, retrieval = augment_chat_request(
        request,
        collection,
        reranker_model,
        default_top_k=default_top_k,
    )

    response = await _forward_request(aug_request, openai_base_url)

    # Add sources to non-streaming response
    if retrieval and not request.stream and isinstance(response, dict):
        response["rag_sources"] = retrieval.sources

    return response


async def _forward_request(
    request: ChatRequest,
    openai_base_url: str,
) -> Any:
    """Forward to backend LLM."""
    # Filter out RAG-specific fields before forwarding
    forward_payload = request.model_dump(exclude={"rag_top_k"})

    if request.stream:

        async def generate() -> AsyncGenerator[str, None]:
            try:
                async with (
                    httpx.AsyncClient(timeout=120.0) as client,
                    client.stream(
                        "POST",
                        f"{openai_base_url}/chat/completions",
                        json=forward_payload,
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
            except Exception as e:
                logger.exception("Streaming error")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{openai_base_url}/chat/completions",
            json=forward_payload,
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
