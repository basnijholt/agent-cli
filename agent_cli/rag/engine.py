"""Core RAG Engine Logic (Functional)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent_cli.core.openai_proxy import forward_chat_request
from agent_cli.rag.models import Message
from agent_cli.rag.retriever import search_context

if TYPE_CHECKING:
    from chromadb import Collection

    from agent_cli.rag.models import ChatRequest, RetrievalResult
    from agent_cli.rag.retriever import OnnxCrossEncoder

LOGGER = logging.getLogger("agent_cli.rag.engine")


def augment_chat_request(
    request: ChatRequest,
    collection: Collection,
    reranker_model: OnnxCrossEncoder,
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
    top_k = request.rag_top_k if request.rag_top_k is not None else default_top_k
    if top_k <= 0:
        LOGGER.info("RAG retrieval disabled for this request (top_k=%s)", top_k)
        return request, None

    retrieval = search_context(
        collection,
        reranker_model,
        user_message,
        top_k=top_k,
    )

    if not retrieval.context:
        LOGGER.info("ℹ️  No relevant context found for query: '%s'", user_message[:50])  # noqa: RUF001
        return request, None

    LOGGER.info(
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
    reranker_model: OnnxCrossEncoder,
    openai_base_url: str,
    default_top_k: int = 3,
    api_key: str | None = None,
) -> Any:
    """Process a chat request with RAG."""
    aug_request, retrieval = augment_chat_request(
        request,
        collection,
        reranker_model,
        default_top_k=default_top_k,
    )

    response = await _forward_request(aug_request, openai_base_url, api_key)

    # Add sources to non-streaming response
    if retrieval and not request.stream and isinstance(response, dict):
        response["rag_sources"] = retrieval.sources

    return response


async def _forward_request(
    request: ChatRequest,
    openai_base_url: str,
    api_key: str | None = None,
) -> Any:
    """Forward to backend LLM."""
    return await forward_chat_request(
        request,
        openai_base_url,
        api_key,
        exclude_fields={"rag_top_k"},
    )
