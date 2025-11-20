"""Core memory engine logic."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from agent_cli.memory.models import ChatRequest, MemoryEntry, MemoryRetrieval, Message
from agent_cli.memory.store import query_memories, upsert_memories

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from chromadb import Collection

logger = logging.getLogger("agent_cli.memory.engine")


def _retrieve_memory(
    collection: Collection,
    *,
    conversation_id: str,
    query: str,
    top_k: int,
) -> MemoryRetrieval:
    results = query_memories(
        collection,
        conversation_id=conversation_id,
        text=query,
        n_results=top_k,
    )

    documents = results.get("documents", [[]])[0] or []
    metadatas = results.get("metadatas", [[]])[0] or []
    distances = results.get("distances", [[]])[0] or []

    entries: list[MemoryEntry] = []
    for idx, doc in enumerate(documents):
        meta = metadatas[idx] if idx < len(metadatas) else {}
        entries.append(
            MemoryEntry(
                role=str(meta.get("role", "unknown")),
                content=str(doc),
                created_at=str(meta.get("created_at", "")),
                score=float(distances[idx]) if idx < len(distances) else None,
            ),
        )

    return MemoryRetrieval(entries=entries)


def augment_chat_request(
    request: ChatRequest,
    collection: Collection,
    default_top_k: int = 5,
    default_memory_id: str = "default",
) -> tuple[ChatRequest, MemoryRetrieval | None, str]:
    """Retrieve memory context and augment the chat request."""
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        None,
    )
    if not user_message:
        return request, None, default_memory_id

    conversation_id = request.memory_id or default_memory_id
    top_k = request.memory_top_k if request.memory_top_k is not None else default_top_k

    if top_k <= 0:
        logger.info("Memory retrieval disabled for this request (top_k=%s)", top_k)
        return request, None, conversation_id

    retrieval = _retrieve_memory(
        collection,
        conversation_id=conversation_id,
        query=user_message,
        top_k=top_k,
    )

    if not retrieval.entries:
        return request, None, conversation_id

    formatted_context = "\n\n---\n\n".join(
        f"[{entry.role}] {entry.content}" for entry in retrieval.entries
    )
    augmented_content = (
        f"Long-term memory (most relevant first):\n{formatted_context}\n\n---\n\n"
        f"Current message: {user_message}"
    )

    augmented_messages = list(request.messages[:-1])
    augmented_messages.append(Message(role="user", content=augmented_content))

    aug_request = request.model_copy()
    aug_request.messages = augmented_messages

    return aug_request, retrieval, conversation_id


def _persist_turn(
    collection: Collection,
    *,
    conversation_id: str,
    user_message: str | None,
    assistant_message: str | None,
) -> None:
    now = datetime.now(UTC).isoformat()
    ids: list[str] = []
    contents: list[str] = []
    metadatas: list[dict[str, str]] = []

    if user_message:
        ids.append(str(uuid4()))
        contents.append(user_message)
        metadatas.append(
            {
                "conversation_id": conversation_id,
                "role": "user",
                "created_at": now,
            },
        )

    if assistant_message:
        ids.append(str(uuid4()))
        contents.append(assistant_message)
        metadatas.append(
            {
                "conversation_id": conversation_id,
                "role": "assistant",
                "created_at": now,
            },
        )

    if ids:
        upsert_memories(collection, ids=ids, contents=contents, metadatas=metadatas)


async def process_chat_request(
    request: ChatRequest,
    collection: Collection,
    openai_base_url: str,
    default_top_k: int = 5,
    api_key: str | None = None,
) -> Any:
    """Process a chat request with long-term memory support."""
    aug_request, retrieval, conversation_id = augment_chat_request(
        request,
        collection,
        default_top_k=default_top_k,
    )

    response = await _forward_request(aug_request, openai_base_url, api_key)

    if not request.stream and isinstance(response, dict):
        # Persist the turn once we have the assistant response
        user_message = next(
            (m.content for m in reversed(request.messages) if m.role == "user"),
            None,
        )
        assistant_message = None
        choices = response.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            assistant_message = msg.get("content")

        _persist_turn(
            collection,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
        )

        response["memory_hits"] = (
            [entry.model_dump() for entry in retrieval.entries] if retrieval else []
        )

    return response


async def _forward_request(
    request: ChatRequest,
    openai_base_url: str,
    api_key: str | None = None,
) -> Any:
    """Forward to backend LLM."""
    forward_payload = request.model_dump(exclude={"memory_id", "memory_top_k"})
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None

    if request.stream:

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
