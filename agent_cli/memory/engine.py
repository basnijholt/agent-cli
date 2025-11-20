"""Core memory engine logic."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx
from fastapi import HTTPException

from agent_cli.core.openai_proxy import forward_chat_request
from agent_cli.memory.files import write_memory_file
from agent_cli.memory.models import (
    ChatRequest,
    MemoryEntry,
    MemoryExtras,
    MemoryMetadata,
    MemoryRetrieval,
    Message,
    StoredMemory,
)
from agent_cli.memory.store import (
    delete_entries,
    get_summary_entry,
    list_conversation_entries,
    query_memories,
    upsert_memories,
)
from agent_cli.rag.retriever import OnnxCrossEncoder, predict_relevance

if TYPE_CHECKING:
    from pathlib import Path

    from chromadb import Collection

logger = logging.getLogger("agent_cli.memory.engine")

_DEFAULT_MAX_ENTRIES = 500
_SUMMARY_DOC_ID_SUFFIX = "::summary"
_DEFAULT_MMR_LAMBDA = 0.7
_DEFAULT_TAG_BOOST = 0.1
_SUMMARY_SHORT_ROLE = "summary_short"
_SUMMARY_LONG_ROLE = "summary_long"


def _safe_identifier(value: str) -> str:
    """File/ID safe token preserving readability."""
    safe = "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in value)
    return safe or "entry"


@dataclass
class WriteEntry:
    """Structured memory entry to persist."""

    role: str
    content: str
    extras: MemoryExtras


def _retrieve_memory(
    collection: Collection,
    *,
    conversation_id: str,
    query: str,
    top_k: int,
    reranker_model: OnnxCrossEncoder,
    include_global: bool = True,
    include_summary: bool = True,
    mmr_lambda: float = _DEFAULT_MMR_LAMBDA,
    tag_boost: float = _DEFAULT_TAG_BOOST,
) -> tuple[MemoryRetrieval, list[str]]:
    candidate_conversations = [conversation_id]
    if include_global and conversation_id != "global":
        candidate_conversations.append("global")

    candidates: list[StoredMemory] = []
    for cid in candidate_conversations:
        records = query_memories(
            collection,
            conversation_id=cid,
            text=query,
            n_results=top_k * 3,
        )
        candidates.extend(records)

    def recency_boost(meta: Any) -> float:
        ts = meta.created_at
        try:
            dt = datetime.fromisoformat(str(ts))
        except Exception:
            return 0.0
        age_days = max((datetime.now(UTC) - dt).total_seconds() / 86400.0, 0.0)
        return 1.0 / (1.0 + age_days / 7.0)

    def salience_boost(meta: Any) -> float:
        sal = meta.salience
        if sal is None:
            return 0.0
        try:
            return float(sal)
        except Exception:
            return 0.0

    def tag_overlap_boost(meta: Any, query_text: str) -> float:
        query_tags = _extract_tags_from_text(query_text)
        meta_tags = set(meta.tags or [])
        if not query_tags or not meta_tags:
            return 0.0
        overlap = len(query_tags & meta_tags)
        return min(overlap, 3) * 0.1

    scores: list[float] = []
    if candidates:
        pairs = [(query, mem.content) for mem in candidates]
        rr_scores = predict_relevance(reranker_model, pairs)
        for mem, rr in zip(candidates, rr_scores, strict=False):
            base = rr
            dist_bonus = 0.0 if mem.distance is None else 1.0 / (1.0 + mem.distance)
            total = (
                base
                + 0.1 * dist_bonus
                + 0.2 * recency_boost(mem.metadata)
                + 0.1 * salience_boost(mem.metadata)
                + tag_boost * tag_overlap_boost(mem.metadata, query)
            )
            scores.append(total)
    else:
        for mem in candidates:
            base = 0.0 if mem.distance is None else 1.0 / (1.0 + mem.distance)
            total = (
                base
                + 0.2 * recency_boost(mem.metadata)
                + 0.1 * salience_boost(mem.metadata)
                + tag_boost * tag_overlap_boost(mem.metadata, query)
            )
            scores.append(total)

    selected = _mmr_select(candidates, scores, max_items=top_k, lambda_mult=mmr_lambda)

    entries: list[MemoryEntry] = [
        MemoryEntry(
            role=mem.metadata.role or "memory",
            content=mem.content,
            created_at=mem.metadata.created_at,
            score=score,
        )
        for mem, score in selected
    ]

    summaries: list[str] = []
    if include_summary:
        summary_short = get_summary_entry(collection, conversation_id, role=_SUMMARY_SHORT_ROLE)
        summary_long = get_summary_entry(collection, conversation_id, role=_SUMMARY_LONG_ROLE)
        if summary_short:
            summaries.append(f"Short summary:\n{summary_short.content}")
        if summary_long:
            summaries.append(f"Long summary:\n{summary_long.content}")

    return MemoryRetrieval(entries=entries), summaries


def _format_augmented_content(
    *,
    user_message: str,
    summaries: list[str],
    memories: list[MemoryEntry],
) -> str:
    parts: list[str] = []
    if summaries:
        parts.append("Conversation summaries:\n" + "\n\n".join(summaries))
    if memories:
        memory_block = "\n\n---\n\n".join(f"[{m.role}] {m.content}" for m in memories)
        parts.append(f"Long-term memory (most relevant first):\n{memory_block}")
    parts.append(f"Current message: {user_message}")
    return "\n\n---\n\n".join(parts)


def augment_chat_request(
    request: ChatRequest,
    collection: Collection,
    reranker_model: OnnxCrossEncoder,
    default_top_k: int = 5,
    default_memory_id: str = "default",
    include_global: bool = True,
    mmr_lambda: float = _DEFAULT_MMR_LAMBDA,
    tag_boost: float = _DEFAULT_TAG_BOOST,
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

    retrieval, summaries = _retrieve_memory(
        collection,
        conversation_id=conversation_id,
        query=user_message,
        top_k=top_k,
        reranker_model=reranker_model,
        include_global=include_global,
        mmr_lambda=mmr_lambda,
        tag_boost=tag_boost,
    )

    if not retrieval.entries and not summaries:
        return request, None, conversation_id

    augmented_content = _format_augmented_content(
        user_message=user_message,
        summaries=summaries,
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
    memory_root: Path,
    conversation_id: str,
    entries: list[WriteEntry | None],
) -> None:
    now = datetime.now(UTC).isoformat()
    ids: list[str] = []
    contents: list[str] = []
    metadatas: list[MemoryMetadata] = []
    for item in entries:
        if item is None:
            continue
        role, content, extras = item.role, item.content, item.extras
        record = write_memory_file(
            memory_root,
            conversation_id=conversation_id,
            role=role,
            created_at=now,
            content=content,
            salience=extras.salience,
            tags=extras.tags,
            doc_id=str(uuid4()),
        )
        ids.append(record.id)
        contents.append(record.content)
        metadatas.append(record.metadata)
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


def _extract_tags_from_text(text: str, *, max_tags: int = 5) -> set[str]:
    """Heuristic tag extraction from text (alpha tokens length>=4)."""
    tokens = []
    for raw in text.split():
        cleaned = "".join(ch for ch in raw.lower() if ch.isalpha())
        if len(cleaned) >= 4:  # noqa: PLR2004
            tokens.append(cleaned)
    unique = []
    seen = set()
    for t in tokens:
        if t not in seen:
            unique.append(t)
            seen.add(t)
        if len(unique) >= max_tags:
            break
    return set(unique)


def _token_overlap_similarity(a: str, b: str) -> float:
    """Simple token overlap similarity for MMR."""
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _mmr_select(
    candidates: list[StoredMemory],
    scores: list[float],
    *,
    max_items: int,
    lambda_mult: float,
) -> list[tuple[StoredMemory, float]]:
    """Apply Maximal Marginal Relevance to promote diversity."""
    if not candidates or max_items <= 0:
        return []

    selected: list[int] = []
    candidate_indices = list(range(len(candidates)))

    # Start with top scorer
    first_idx = max(candidate_indices, key=lambda i: scores[i])
    selected.append(first_idx)
    candidate_indices.remove(first_idx)

    while candidate_indices and len(selected) < max_items:
        best_idx = None
        best_score = float("-inf")
        for idx in candidate_indices:
            relevance = scores[idx]
            redundancy = max(
                (
                    _token_overlap_similarity(candidates[idx].content, candidates[s].content)
                    for s in selected
                ),
                default=0.0,
            )
            mmr_score = lambda_mult * relevance - (1 - lambda_mult) * redundancy
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx
        if best_idx is None:
            break
        selected.append(best_idx)
        candidate_indices.remove(best_idx)

    return [(candidates[i], scores[i]) for i in selected]


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


async def _update_summaries(
    *,
    prior_short: str | None,
    prior_long: str | None,
    new_facts: list[str],
    openai_base_url: str,
    api_key: str | None,
    model: str,
) -> tuple[str | None, str | None]:
    """Update both short and long summaries."""
    short = await _update_summary(
        prior_summary=prior_short,
        new_facts=new_facts,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
        max_tokens=256,
    )
    long = await _update_summary(
        prior_summary=prior_long,
        new_facts=new_facts,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
        max_tokens=512,
    )
    return short, long


def _persist_summary(
    collection: Collection,
    *,
    memory_root: Path,
    conversation_id: str,
    summary: str,
    role: str,
) -> None:
    now = datetime.now(UTC).isoformat()
    doc_id = _safe_identifier(f"{conversation_id}{_SUMMARY_DOC_ID_SUFFIX}-{role}")
    record = write_memory_file(
        memory_root,
        conversation_id=conversation_id,
        role=role,
        created_at=now,
        content=summary,
        summary_kind=role,
        doc_id=doc_id,
    )
    upsert_memories(
        collection,
        ids=[record.id],
        contents=[record.content],
        metadatas=[record.metadata],
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
            key=lambda e: e.metadata.created_at,
        )
    except Exception:
        sorted_entries = entries
    overflow = sorted_entries[:-max_entries]
    delete_entries(collection, [e.id for e in overflow if e.id])


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
    tag_boost: float = _DEFAULT_TAG_BOOST,
) -> Any:
    """Process a chat request with long-term memory support."""
    aug_request, retrieval, conversation_id = augment_chat_request(
        request,
        collection,
        reranker_model=reranker_model,
        default_top_k=default_top_k,
        mmr_lambda=mmr_lambda,
        tag_boost=tag_boost,
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
            memory_root=memory_root,
            conversation_id=conversation_id,
            entries=[
                WriteEntry(
                    role="user",
                    content=user_message,
                    extras=MemoryExtras(),
                )
                if user_message
                else None,
                WriteEntry(
                    role="assistant",
                    content=assistant_message,
                    extras=MemoryExtras(),
                )
                if assistant_message
                else None,
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
                fact_entries: list[WriteEntry] = [
                    WriteEntry(
                        role="memory",
                        content=fact,
                        extras=MemoryExtras(
                            salience=1.0,
                            tags=list(_extract_tags_from_text(fact)),
                        ),
                    )
                    for fact in facts
                ]
                _persist_entries(
                    collection,
                    memory_root=memory_root,
                    conversation_id=conversation_id,
                    entries=list(fact_entries),
                )
                prior_summary_entry = get_summary_entry(
                    collection,
                    conversation_id,
                    role=_SUMMARY_SHORT_ROLE,
                )
                prior_long_entry = get_summary_entry(
                    collection,
                    conversation_id,
                    role=_SUMMARY_LONG_ROLE,
                )
                prior_summary = prior_summary_entry.content if prior_summary_entry else None
                prior_long = prior_long_entry.content if prior_long_entry else None
                new_short, new_long = await _update_summaries(
                    prior_short=prior_summary,
                    prior_long=prior_long,
                    new_facts=facts,
                    openai_base_url=openai_base_url,
                    api_key=api_key,
                    model=request.model,
                )
                if new_short:
                    _persist_summary(
                        collection,
                        memory_root=memory_root,
                        conversation_id=conversation_id,
                        summary=new_short,
                        role=_SUMMARY_SHORT_ROLE,
                    )
                if new_long:
                    _persist_summary(
                        collection,
                        memory_root=memory_root,
                        conversation_id=conversation_id,
                        summary=new_long,
                        role=_SUMMARY_LONG_ROLE,
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
    return await forward_chat_request(
        request,
        openai_base_url,
        api_key,
        exclude_fields={"memory_id", "memory_top_k"},
    )
