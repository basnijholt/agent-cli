"""Core memory engine logic."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi.responses import StreamingResponse

from agent_cli.core.openai_proxy import forward_chat_request
from agent_cli.memory import _streaming
from agent_cli.memory._git import commit_changes
from agent_cli.memory._ingest import extract_and_store_facts_and_summaries
from agent_cli.memory._persistence import evict_if_needed, persist_entries
from agent_cli.memory._retrieval import augment_chat_request
from agent_cli.memory._tasks import run_in_background
from agent_cli.memory.entities import Turn

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping
    from pathlib import Path

    from chromadb import Collection

    from agent_cli.core.reranker import OnnxCrossEncoder
    from agent_cli.memory.models import ChatRequest

LOGGER = logging.getLogger(__name__)

_DEFAULT_MAX_ENTRIES = 500
_DEFAULT_MMR_LAMBDA = 0.7


def _elapsed_ms(start: float) -> float:
    """Return elapsed milliseconds since start."""
    return (perf_counter() - start) * 1000


def _latest_user_message(request: ChatRequest) -> str | None:
    """Return the most recent user message, if any."""
    return next((m.content for m in reversed(request.messages) if m.role == "user"), None)


def _assistant_reply_content(response: Mapping[str, Any]) -> str | None:
    """Extract assistant content from a chat completion response."""
    choices = response.get("choices", [])
    if not choices:
        return None
    message = choices[0].get("message")
    assert message is not None
    return message.get("content")


def _persist_turns(
    collection: Collection,
    *,
    memory_root: Path,
    conversation_id: str,
    user_message: str | None,
    assistant_message: str | None,
    user_turn_id: str | None = None,
) -> None:
    """Persist the latest user/assistant exchanges."""
    now = datetime.now(UTC)
    entries: list[Turn | None] = []

    if user_message:
        entries.append(
            Turn(
                id=user_turn_id or str(uuid4()),
                conversation_id=conversation_id,
                role="user",
                content=user_message,
                created_at=now,
            ),
        )

    if assistant_message:
        entries.append(
            Turn(
                id=str(uuid4()),
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_message,
                created_at=now,
            ),
        )

    persist_entries(
        collection,
        memory_root=memory_root,
        conversation_id=conversation_id,
        entries=entries,  # type: ignore[arg-type]
    )


async def _postprocess_after_turn(
    *,
    collection: Collection,
    memory_root: Path,
    conversation_id: str,
    user_message: str | None,
    assistant_message: str | None,
    openai_base_url: str,
    api_key: str | None,
    enable_summarization: bool,
    model: str,
    max_entries: int,
    enable_git_versioning: bool,
    user_turn_id: str | None = None,
) -> None:
    """Run summarization/fact extraction and eviction."""
    post_start = perf_counter()
    summary_start = perf_counter()
    await extract_and_store_facts_and_summaries(
        collection=collection,
        memory_root=memory_root,
        conversation_id=conversation_id,
        user_message=user_message,
        assistant_message=assistant_message,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
        enable_git_versioning=enable_git_versioning,
        source_id=user_turn_id,
        enable_summarization=enable_summarization,
    )
    LOGGER.info(
        "Updated facts and summaries in %.1f ms (conversation=%s)",
        _elapsed_ms(summary_start),
        conversation_id,
    )
    eviction_start = perf_counter()
    evict_if_needed(collection, memory_root, conversation_id, max_entries)
    LOGGER.info(
        "Eviction check completed in %.1f ms (conversation=%s)",
        _elapsed_ms(eviction_start),
        conversation_id,
    )
    LOGGER.info(
        "Post-processing finished in %.1f ms (conversation=%s, summarization=%s)",
        _elapsed_ms(post_start),
        conversation_id,
        "enabled" if enable_summarization else "disabled",
    )

    if enable_git_versioning:
        await commit_changes(memory_root, f"Update memory for conversation {conversation_id}")


async def _stream_and_persist_response(
    *,
    forward_payload: dict[str, Any],
    collection: Collection,
    memory_root: Path,
    conversation_id: str,
    user_message: str | None,
    openai_base_url: str,
    api_key: str | None,
    enable_summarization: bool,
    model: str,
    max_entries: int,
    enable_git_versioning: bool,
    user_turn_id: str | None = None,
) -> StreamingResponse:
    """Forward streaming request, tee assistant text, and persist after completion."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    stream_start = perf_counter()

    async def _persist_stream_result(assistant_message: str | None) -> None:
        post_start = perf_counter()
        _persist_turns(
            collection,
            memory_root=memory_root,
            conversation_id=conversation_id,
            user_message=None,
            assistant_message=assistant_message,
            user_turn_id=None,  # Assistant turn doesn't reuse user ID
        )
        await _postprocess_after_turn(
            collection=collection,
            memory_root=memory_root,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
            openai_base_url=openai_base_url,
            api_key=api_key,
            enable_summarization=enable_summarization,
            model=model,
            max_entries=max_entries,
            enable_git_versioning=enable_git_versioning,
            user_turn_id=user_turn_id,
        )
        LOGGER.info(
            "Stream post-processing completed in %.1f ms (conversation=%s)",
            _elapsed_ms(post_start),
            conversation_id,
        )

    async def tee_and_accumulate() -> AsyncGenerator[str, None]:
        assistant_chunks: list[str] = []
        async for line in _streaming.stream_chat_sse(
            openai_base_url=openai_base_url,
            payload=forward_payload,
            headers=headers,
        ):
            _streaming.accumulate_assistant_text(line, assistant_chunks)
            yield line + "\n\n"
        assistant_message = "".join(assistant_chunks).strip() or None
        if assistant_message:
            run_in_background(
                _persist_stream_result(assistant_message),
                label=f"stream-postprocess-{conversation_id}",
            )
        LOGGER.info(
            "Streaming response finished in %.1f ms (conversation=%s)",
            _elapsed_ms(stream_start),
            conversation_id,
        )

    return StreamingResponse(tee_and_accumulate(), media_type="text/event-stream")


async def process_chat_request(
    request: ChatRequest,
    collection: Collection,
    memory_root: Path,
    openai_base_url: str,
    reranker_model: OnnxCrossEncoder,
    default_top_k: int = 5,
    api_key: str | None = None,
    enable_summarization: bool = True,
    max_entries: int = _DEFAULT_MAX_ENTRIES,
    mmr_lambda: float = _DEFAULT_MMR_LAMBDA,
    recency_weight: float = 0.2,
    score_threshold: float | None = None,
    postprocess_in_background: bool = True,
    enable_git_versioning: bool = False,
    filters: dict[str, Any] | None = None,
) -> Any:
    """Process a chat request with long-term memory support."""
    overall_start = perf_counter()
    retrieval_start = perf_counter()
    aug_request, retrieval, conversation_id, _summaries = await augment_chat_request(
        request,
        collection,
        reranker_model=reranker_model,
        default_top_k=default_top_k,
        include_global=True,
        mmr_lambda=mmr_lambda,
        recency_weight=recency_weight,
        score_threshold=score_threshold,
        filters=filters,
    )
    retrieval_ms = _elapsed_ms(retrieval_start)
    hit_count = len(retrieval.entries) if retrieval else 0
    LOGGER.info(
        "Memory retrieval completed in %.1f ms (conversation=%s, hits=%d, top_k=%d)",
        retrieval_ms,
        conversation_id,
        hit_count,
        request.memory_top_k if request.memory_top_k is not None else default_top_k,
    )

    user_turn_id = str(uuid4())

    if request.stream:
        LOGGER.info(
            "Forwarding streaming request (conversation=%s, model=%s)",
            conversation_id,
            request.model,
        )
        user_message = _latest_user_message(request)
        _persist_turns(
            collection,
            memory_root=memory_root,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=None,
            user_turn_id=user_turn_id,
        )
        forward_payload = aug_request.model_dump(exclude={"memory_id", "memory_top_k"})
        return await _stream_and_persist_response(
            forward_payload=forward_payload,
            collection=collection,
            memory_root=memory_root,
            conversation_id=conversation_id,
            user_message=user_message,
            openai_base_url=openai_base_url,
            api_key=api_key,
            enable_summarization=enable_summarization,
            model=request.model,
            max_entries=max_entries,
            enable_git_versioning=enable_git_versioning,
            user_turn_id=user_turn_id,
        )

    llm_start = perf_counter()
    response = await forward_chat_request(
        aug_request,
        openai_base_url,
        api_key,
        exclude_fields={"memory_id", "memory_top_k"},
    )
    LOGGER.info(
        "LLM completion finished in %.1f ms (conversation=%s, model=%s)",
        _elapsed_ms(llm_start),
        conversation_id,
        request.model,
    )

    if not isinstance(response, dict):
        return response

    user_message = _latest_user_message(request)
    assistant_message = _assistant_reply_content(response)

    _persist_turns(
        collection,
        memory_root=memory_root,
        conversation_id=conversation_id,
        user_message=user_message,
        assistant_message=assistant_message,
        user_turn_id=user_turn_id,
    )

    async def run_postprocess() -> None:
        await _postprocess_after_turn(
            collection=collection,
            memory_root=memory_root,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
            openai_base_url=openai_base_url,
            api_key=api_key,
            enable_summarization=enable_summarization,
            model=request.model,
            max_entries=max_entries,
            enable_git_versioning=enable_git_versioning,
            user_turn_id=user_turn_id,
        )

    if postprocess_in_background:
        run_in_background(run_postprocess(), label=f"postprocess-{conversation_id}")
    else:
        await run_postprocess()

    response["memory_hits"] = (
        [entry.model_dump() for entry in retrieval.entries] if retrieval else []
    )
    LOGGER.info(
        "Request finished in %.1f ms (conversation=%s, hits=%d)",
        _elapsed_ms(overall_start),
        conversation_id,
        hit_count,
    )

    return response
