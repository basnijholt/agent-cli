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
from agent_cli.memory.store import (
    delete_entries,
    get_summary_entry,
    list_conversation_entries,
    query_memories,
    upsert_memories,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from chromadb import Collection

logger = logging.getLogger("agent_cli.memory.engine")

_DEFAULT_MAX_ENTRIES = 500
_SUMMARY_DOC_ID_SUFFIX = "::summary"


def _retrieve_memory(
    collection: Collection,
    *,
    conversation_id: str,
    query: str,
    top_k: int,
    include_summary: bool = True,
) -> tuple[MemoryRetrieval, str | None]:
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
                role=str(meta.get("role", "memory")),
                content=str(doc),
                created_at=str(meta.get("created_at", "")),
                score=float(distances[idx]) if idx < len(distances) else None,
            ),
        )

    summary_text: str | None = None
    if include_summary:
        summary = get_summary_entry(collection, conversation_id)
        if summary:
            summary_text = str(summary["document"])

    return MemoryRetrieval(entries=entries), summary_text


def _format_augmented_content(
    *,
    user_message: str,
    summary_text: str | None,
    memories: list[MemoryEntry],
) -> str:
    parts: list[str] = []
    if summary_text:
        parts.append(f"Conversation summary:\n{summary_text}")
    if memories:
        memory_block = "\n\n---\n\n".join(f"[{m.role}] {m.content}" for m in memories)
        parts.append(f"Long-term memory (most relevant first):\n{memory_block}")
    parts.append(f"Current message: {user_message}")
    return "\n\n---\n\n".join(parts)


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

    retrieval, summary_text = _retrieve_memory(
        collection,
        conversation_id=conversation_id,
        query=user_message,
        top_k=top_k,
    )

    if not retrieval.entries and not summary_text:
        return request, None, conversation_id

    augmented_content = _format_augmented_content(
        user_message=user_message,
        summary_text=summary_text,
        memories=retrieval.entries,
    )

    augmented_messages = list(request.messages[:-1])
    augmented_messages.append(Message(role="user", content=augmented_content))

    aug_request = request.model_copy()
    aug_request.messages = augmented_messages

    return aug_request, retrieval, conversation_id


def _persist_entries(
    collection: Collection,
    *,
    conversation_id: str,
    entries: list[tuple[str, str] | None],  # list of (role, content)
) -> None:
    now = datetime.now(UTC).isoformat()
    ids: list[str] = []
    contents: list[str] = []
    metadatas: list[dict[str, str]] = []
    for item in entries:
        if item is None:
            continue
        role, content = item
        ids.append(str(uuid4()))
        contents.append(content)
        metadatas.append(
            {
                "conversation_id": conversation_id,
                "role": role,
                "created_at": now,
            },
        )
    if ids:
        upsert_memories(collection, ids=ids, contents=contents, metadatas=metadatas)


async def _chat_completion_request(
    *,
    messages: list[dict[str, str]],
    openai_base_url: str,
    api_key: str | None,
    model: str,
    temperature: float = 0.2,
    max_tokens: int = 256,
) -> str:
    """Call backend LLM for a one-shot completion and return content."""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{openai_base_url.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
        )
    if response.status_code != 200:  # noqa: PLR2004
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Upstream error during memory summarization: {response.text}",
        )
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "") or ""


def _parse_bullets(text: str) -> list[str]:
    """Parse bullet lines from LLM output."""
    lines = []
    for raw in text.splitlines():
        line = raw.strip(" -*•\t")
        if line:
            lines.append(line)
    return lines


async def _extract_salient_facts(
    *,
    user_message: str | None,
    assistant_message: str | None,
    openai_base_url: str,
    api_key: str | None,
    model: str,
) -> list[str]:
    if not user_message and not assistant_message:
        return []
    prompt = (
        "You are a memory extractor. From the latest exchange, extract 1-3 succinct facts "
        "that would be useful to remember for future turns. Keep each fact standalone."
    )
    exchange = []
    if user_message:
        exchange.append(f"User: {user_message}")
    if assistant_message:
        exchange.append(f"Assistant: {assistant_message}")
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "\n".join(exchange)},
    ]
    content = await _chat_completion_request(
        messages=messages,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
        temperature=0.0,
        max_tokens=200,
    )
    return _parse_bullets(content)


async def _update_summary(
    *,
    prior_summary: str | None,
    new_facts: list[str],
    openai_base_url: str,
    api_key: str | None,
    model: str,
    max_tokens: int = 256,
) -> str | None:
    if not new_facts:
        return prior_summary
    system_prompt = (
        "You are a concise conversation summarizer. Update the running summary with the new facts. "
        "Keep it brief and focused on enduring information."
    )
    user_parts = []
    if prior_summary:
        user_parts.append(f"Previous summary:\n{prior_summary}")
    user_parts.append("New facts:\n" + "\n".join(f"- {fact}" for fact in new_facts))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
    return await _chat_completion_request(
        messages=messages,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
        temperature=0.2,
        max_tokens=max_tokens,
    )


def _persist_summary(
    collection: Collection,
    *,
    conversation_id: str,
    summary: str,
) -> None:
    now = datetime.now(UTC).isoformat()
    upsert_memories(
        collection,
        ids=[f"{conversation_id}{_SUMMARY_DOC_ID_SUFFIX}"],
        contents=[summary],
        metadatas=[
            {
                "conversation_id": conversation_id,
                "role": "summary",
                "created_at": now,
            },
        ],
    )


def _evict_if_needed(collection: Collection, conversation_id: str, max_entries: int) -> None:
    """Evict oldest non-summary entries beyond the max budget."""
    if max_entries <= 0:
        return
    entries = list_conversation_entries(collection, conversation_id, include_summary=False)
    if len(entries) <= max_entries:
        return
    # Sort by created_at asc
    try:
        sorted_entries = sorted(
            entries,
            key=lambda e: e["metadata"].get("created_at", ""),
        )
    except Exception:
        sorted_entries = entries
    overflow = sorted_entries[:-max_entries]
    delete_entries(collection, [e["id"] for e in overflow])


async def process_chat_request(
    request: ChatRequest,
    collection: Collection,
    openai_base_url: str,
    default_top_k: int = 5,
    api_key: str | None = None,
    enable_summarization: bool = True,
    max_entries: int = _DEFAULT_MAX_ENTRIES,
) -> Any:
    """Process a chat request with long-term memory support."""
    aug_request, retrieval, conversation_id = augment_chat_request(
        request,
        collection,
        default_top_k=default_top_k,
    )

    response = await _forward_request(aug_request, openai_base_url, api_key)

    if not request.stream and isinstance(response, dict):
        user_message = next(
            (m.content for m in reversed(request.messages) if m.role == "user"),
            None,
        )
        assistant_message = None
        choices = response.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            assistant_message = msg.get("content")

        # Persist raw turns
        _persist_entries(
            collection,
            conversation_id=conversation_id,
            entries=[
                ("user", user_message) if user_message else None,
                ("assistant", assistant_message) if assistant_message else None,
            ],
        )

        memory_hits = [entry.model_dump() for entry in retrieval.entries] if retrieval else []

        if enable_summarization:
            facts = await _extract_salient_facts(
                user_message=user_message,
                assistant_message=assistant_message,
                openai_base_url=openai_base_url,
                api_key=api_key,
                model=request.model,
            )
            if facts:
                _persist_entries(
                    collection,
                    conversation_id=conversation_id,
                    entries=[("memory", fact) for fact in facts],
                )
                prior_summary_entry = get_summary_entry(collection, conversation_id)
                prior_summary = (
                    str(prior_summary_entry["document"])
                    if prior_summary_entry and prior_summary_entry.get("document")
                    else None
                )
                new_summary = await _update_summary(
                    prior_summary=prior_summary,
                    new_facts=facts,
                    openai_base_url=openai_base_url,
                    api_key=api_key,
                    model=request.model,
                )
                if new_summary:
                    _persist_summary(
                        collection,
                        conversation_id=conversation_id,
                        summary=new_summary,
                    )

        _evict_if_needed(collection, conversation_id, max_entries)
        response["memory_hits"] = memory_hits

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
