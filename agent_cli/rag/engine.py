"""Core RAG Engine Logic (Functional)."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator  # noqa: TC003
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING, Any

from fastapi.responses import StreamingResponse
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from agent_cli.core.sse import format_chunk, format_done
from agent_cli.rag.models import Message, RetrievalResult  # noqa: TC001
from agent_cli.rag.retriever import search_context
from agent_cli.rag.utils import load_document_text

if TYPE_CHECKING:
    from chromadb import Collection
    from pydantic_ai.result import RunResult

    from agent_cli.rag.models import ChatRequest
    from agent_cli.rag.retriever import OnnxCrossEncoder

LOGGER = logging.getLogger(__name__)

# Maximum context size in characters (~3000 tokens at 4 chars/token)
_MAX_CONTEXT_CHARS = 12000

_RAG_SYSTEM_TEMPLATE = """You are a helpful assistant with access to documentation.

## Instructions
- Use the retrieved context ONLY if it's relevant to the question
- If the context is irrelevant, ignore it and answer based on your knowledge (or say you don't know)
- When using context, cite sources: [Source: filename]
- If snippets are insufficient, call read_full_document(file_path) to get full content

## Retrieved Context
The following was automatically retrieved based on the user's query. It may or may not be relevant:

{context}"""


def truncate_context(context: str, max_chars: int = _MAX_CONTEXT_CHARS) -> str:
    """Truncate context to fit within token budget while keeping complete chunks.

    Args:
        context: Raw context string with chunks separated by "---".
        max_chars: Maximum characters to keep (default ~3000 tokens).

    Returns:
        Truncated context with complete chunks only.

    """
    if len(context) <= max_chars:
        return context

    separator = "\n\n---\n\n"
    chunks = context.split(separator)
    result = []
    total = 0

    for chunk in chunks:
        chunk_len = len(chunk) + len(separator)
        if total + chunk_len > max_chars:
            break
        result.append(chunk)
        total += chunk_len

    return separator.join(result)


def is_path_safe(base: Path, requested: Path) -> bool:
    """Check if requested path is safely within base directory.

    Args:
        base: The allowed base directory.
        requested: The path to validate.

    Returns:
        True if requested path is within base, False otherwise.

    """
    try:
        requested.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


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

    retrieval = search_context(collection, reranker_model, user_message, top_k=top_k)

    if not retrieval.context:
        LOGGER.info("ℹ️  No relevant context found for query: '%s'", user_message[:50])  # noqa: RUF001
        return None

    LOGGER.info(
        "✅ Found %d relevant sources for query: '%s'",
        len(retrieval.sources),
        user_message[:50],
    )
    return retrieval


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
    usage = result.usage()
    response: dict[str, Any] = {
        "id": f"chatcmpl-{result.run_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.output},
                "finish_reason": "stop",
            },
        ],
    }

    if usage:
        response["usage"] = {
            "prompt_tokens": usage.input_tokens or 0,
            "completion_tokens": usage.output_tokens or 0,
            "total_tokens": usage.total_tokens or 0,
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
    retrieval = retrieve_context(request, collection, reranker_model, default_top_k=default_top_k)

    # 2. Define Tool
    def read_full_document(file_path: str) -> str:
        """Read the full content of a document by its path.

        Use this tool when the context snippet is insufficient and you need
        the complete document to answer the user's question accurately.
        The file_path should match one of the [Source: ...] paths from the context.
        """
        try:
            full_path = (docs_folder / file_path).resolve()
            if not is_path_safe(docs_folder, full_path):
                return "Error: Access denied. Path is outside the document folder."
            if not full_path.exists():
                return f"Error: File not found: {file_path}"

            text = load_document_text(full_path)
            if text is None:
                return "Error: Could not read file (unsupported format or encoding)."
            return text
        except Exception as e:
            return f"Error reading file: {e}"

    # 3. Define System Prompt
    system_prompt = ""
    if retrieval and retrieval.context:
        truncated = truncate_context(retrieval.context)
        system_prompt = _RAG_SYSTEM_TEMPLATE.format(context=truncated)

    # 4. Setup Agent
    provider = OpenAIProvider(base_url=openai_base_url, api_key=api_key or "dummy")
    model = OpenAIModel(model_name=request.model, provider=provider)

    agent = Agent(model=model, tools=[read_full_document], system_prompt=system_prompt)

    # 5. Prepare Message History & Prompt
    history, user_prompt = _convert_messages(request.messages)

    # 6. Model Settings
    model_settings = _extract_model_settings(request)

    # 7. Run Agent
    if request.stream:
        return StreamingResponse(
            _stream_generator(
                agent,
                user_prompt,
                history,
                model_settings,
                request.model,
                retrieval,
            ),
            media_type="text/event-stream",
        )

    result = await agent.run(
        user_prompt,
        message_history=history,
        model_settings=model_settings,
    )

    return _build_openai_response(result, request.model, retrieval)


async def _stream_generator(
    agent: Agent,
    prompt: str,
    history: list[ModelRequest | ModelResponse],
    settings: dict[str, Any],
    model_name: str,
    retrieval: RetrievalResult | None,
) -> AsyncGenerator[str, None]:
    """Stream Pydantic AI result as OpenAI SSE."""
    async with agent.run_stream(prompt, message_history=history, model_settings=settings) as result:
        async for chunk in result.stream_text(delta=True):
            yield format_chunk(result.run_id, model_name, content=chunk)

        # Finish chunk with optional RAG sources
        extra = None
        if retrieval and retrieval.sources:
            extra = {
                "rag_sources": [
                    {"source": s.source, "path": s.path, "chunk_id": s.chunk_id, "score": s.score}
                    for s in retrieval.sources
                ],
            }
        yield format_chunk(result.run_id, model_name, finish_reason="stop", extra=extra)
        yield format_done()
