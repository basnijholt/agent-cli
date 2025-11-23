"""Core RAG Engine Logic (Functional)."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator  # noqa: TC003
from typing import TYPE_CHECKING, Any

from fastapi.responses import StreamingResponse
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from agent_cli.rag.models import RAGDeps
from agent_cli.rag.retriever import search_context
from agent_cli.rag.tools import read_full_document

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection
    from pydantic_ai.result import RunResult

    from agent_cli.rag.models import ChatRequest, Message, RetrievalResult
    from agent_cli.rag.retriever import OnnxCrossEncoder

LOGGER = logging.getLogger(__name__)


def retrieve_context(
    request: ChatRequest,
    collection: Collection,
    reranker_model: OnnxCrossEncoder,
    default_top_k: int = 3,
) -> RetrievalResult | None:
    """Retrieve context for the request.

    Returns:
        The retrieval result, or None if no retrieval was performed.

    """
    # Get last user message
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        None,
    )

    if not user_message:
        return None

    # Retrieve
    top_k = request.rag_top_k if request.rag_top_k is not None else default_top_k
    if top_k <= 0:
        LOGGER.info("RAG retrieval disabled for this request (top_k=%s)", top_k)
        return None

    retrieval = search_context(
        collection,
        reranker_model,
        user_message,
        top_k=top_k,
    )

    if not retrieval.context:
        LOGGER.info("ℹ️  No relevant context found for query: '%s'", user_message[:50])  # noqa: RUF001
        return None

    LOGGER.info(
        "✅ Found %d relevant sources for query: '%s'",
        len(retrieval.sources),
        user_message[:50],
    )
    return retrieval


# Define the Agent globally.
# We use a dummy model here because we override it dynamically per-request.
# We must set a dummy API key to satisfy Pydantic AI's validation at import time.
# We instantiate the model explicitly to bypass the environment check.
_dummy_provider = OpenAIProvider(api_key="dummy")
rag_agent = Agent(
    OpenAIModel("gpt-4o", provider=_dummy_provider),
    deps_type=RAGDeps,
    tools=[read_full_document],
)


@rag_agent.system_prompt
def _inject_context(ctx: RunContext[RAGDeps]) -> str:
    if ctx.deps.rag_context:
        return f"Context from documentation:\n{ctx.deps.rag_context}"
    return ""


def _convert_messages(
    messages: list[Message],
) -> tuple[list[ModelRequest | ModelResponse], str]:
    """Convert OpenAI messages to Pydantic AI messages and extract user prompt."""
    pyd_messages: list[ModelRequest | ModelResponse] = []

    # Validation: Ensure there is at least one message
    if not messages:
        return [], ""

    # Split history and last user prompt
    history_msgs = messages[:-1]
    last_msg = messages[-1]

    for m in history_msgs:
        if m.role == "system":
            pyd_messages.append(ModelRequest(parts=[SystemPromptPart(content=m.content)]))
        elif m.role == "user":
            pyd_messages.append(ModelRequest(parts=[UserPromptPart(content=m.content)]))
        elif m.role == "assistant":
            pyd_messages.append(ModelResponse(parts=[TextPart(content=m.content)]))

    return pyd_messages, last_msg.content


def _extract_model_settings(request: ChatRequest) -> dict[str, Any]:
    """Extract model settings from request."""
    settings = {}
    if request.temperature is not None:
        settings["temperature"] = request.temperature
    if request.max_tokens is not None:
        settings["max_tokens"] = request.max_tokens
    return settings


def _build_openai_response(
    result: RunResult,
    model_name: str,
    retrieval: RetrievalResult | None,
) -> dict[str, Any]:
    """Format the Pydantic AI result as an OpenAI-compatible dict."""
    response = {
        "id": f"chatcmpl-{result.run_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.output,
                },
                "finish_reason": "stop",
            },
        ],
        "usage": {
            "prompt_tokens": result.usage.request_tokens if result.usage else 0,
            "completion_tokens": result.usage.response_tokens if result.usage else 0,
            "total_tokens": result.usage.total_tokens if result.usage else 0,
        },
    }

    if retrieval:
        response["rag_sources"] = retrieval.sources

    return response


async def process_chat_request(
    request: ChatRequest,
    collection: Collection,
    reranker_model: OnnxCrossEncoder,
    openai_base_url: str,
    docs_folder: Path,
    default_top_k: int = 3,
    api_key: str | None = None,
) -> Any:
    """Process a chat request with RAG."""
    # 1. Retrieve Context
    retrieval = retrieve_context(
        request,
        collection,
        reranker_model,
        default_top_k=default_top_k,
    )

    # 2. Setup Dynamic Model
    provider = OpenAIProvider(base_url=openai_base_url, api_key=api_key or "dummy")
    model = OpenAIModel(model_name=request.model, provider=provider)

    # 3. Prepare Dependencies
    deps = RAGDeps(
        docs_folder=docs_folder,
        rag_context=retrieval.context if retrieval else None,
    )

    # 4. Prepare Message History & Prompt
    history, user_prompt = _convert_messages(request.messages)

    # 5. Model Settings
    model_settings = _extract_model_settings(request)

    # 6. Run Agent
    if request.stream:
        return StreamingResponse(
            _stream_generator(
                rag_agent,
                user_prompt,
                history,
                deps,
                model_settings,
                request.model,
                model,
            ),
            media_type="text/event-stream",
        )

    result = await rag_agent.run(
        user_prompt,
        message_history=history,
        deps=deps,
        model_settings=model_settings,
        model=model,
    )

    return _build_openai_response(result, request.model, retrieval)


async def _stream_generator(
    agent: Agent,
    prompt: str,
    history: list[ModelRequest | ModelResponse],
    deps: RAGDeps,
    settings: dict[str, Any],
    model_name: str,
    model: OpenAIModel,
) -> AsyncGenerator[str, None]:
    """Stream Pydantic AI result as OpenAI SSE."""
    async with agent.run_stream(
        prompt,
        message_history=history,
        deps=deps,
        model_settings=settings,
        model=model,
    ) as result:
        async for chunk in result.stream_text(delta=True):
            data = {
                "id": f"chatcmpl-{result.run_id}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk},
                        "finish_reason": None,
                    },
                ],
            }
            yield f"data: {json.dumps(data)}\n\n"

        # Finish chunk
        finish_data = {
            "id": f"chatcmpl-{result.run_id}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                },
            ],
        }
        yield f"data: {json.dumps(finish_data)}\n\n"
        yield "data: [DONE]\n\n"
