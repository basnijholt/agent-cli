"""Core memory engine logic."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx
from fastapi.responses import StreamingResponse
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from agent_cli.core.openai_proxy import forward_chat_request
from agent_cli.memory.files import write_memory_file
from agent_cli.memory.models import (
    ChatRequest,
    FactOutput,
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
from agent_cli.memory.tasks import run_in_background
from agent_cli.rag.retriever import OnnxCrossEncoder, predict_relevance

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping
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


def _elapsed_ms(start: float) -> float:
    """Return elapsed milliseconds since start."""
    return (perf_counter() - start) * 1000


def _parse_iso(date_str: str) -> datetime | None:
    """Best-effort ISO8601 parser."""
    try:
        return datetime.fromisoformat(date_str)
    except Exception:
        return None


def _canonical_fact_key(text: str) -> str | None:
    """Heuristic subject/predicate key to consolidate duplicate or conflicting facts."""
    cleaned = re.sub(r"\s+", " ", text.strip()).strip(" .?!;")
    if not cleaned:
        return None
    lowered = cleaned.lower()
    separators = [
        " is ",
        " was ",
        " are ",
        " were ",
        " has ",
        " have ",
        " likes ",
        " loves ",
    ]
    for sep in separators:
        if sep in lowered:
            subject, rest = lowered.split(sep, 1)
            subject = subject.strip()
            predicate = rest.strip()
            if subject and predicate:
                return f"{subject}::{predicate}"
    return lowered


def _canonical_fact_key_from_output(item: FactOutput) -> str | None:
    """Build a key from structured subject/predicate."""
    subject = item.subject.strip().lower()
    predicate = item.predicate.strip().lower()
    if subject and predicate:
        return f"{subject}::{predicate}"
    return None


def _output_to_text(item: FactOutput) -> str:
    """Human-readable fact text from a structured fact."""
    parts = [item.subject, item.predicate, item.object or ""]
    return " ".join(p for p in parts if p).strip()


def _ensure_fact_key(
    fact_key: str | None,
    fact_text: str,
    item: FactOutput | None = None,
) -> str | None:
    """Derive a stable fact_key or return None if impossible."""
    return (
        fact_key
        or (_canonical_fact_key_from_output(item) if item else None)
        or _canonical_fact_key(fact_text)
    )


@dataclass
class WriteEntry:
    """Structured memory entry to persist."""

    role: str
    content: str
    extras: MemoryExtras


@dataclass
class FactCandidate:
    """Structured fact output from extraction."""

    content: str
    fact_key: str


def _dedupe_by_fact_key(candidates: list[StoredMemory]) -> list[StoredMemory]:
    """Keep latest entry per fact_key while leaving unkeyed entries untouched."""
    latest: dict[str, StoredMemory] = {}
    unkeyed: list[StoredMemory] = []

    def _is_newer(a: StoredMemory, b: StoredMemory) -> bool:
        adt = _parse_iso(a.metadata.created_at)
        bdt = _parse_iso(b.metadata.created_at)
        if adt and bdt:
            return adt >= bdt
        return (a.metadata.created_at or "") >= (b.metadata.created_at or "")

    for mem in candidates:
        key = mem.metadata.fact_key
        if not key:
            unkeyed.append(mem)
            continue
        current = latest.get(key)
        if current is None or _is_newer(mem, current):
            latest[key] = mem

    return unkeyed + list(latest.values())


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

    candidates = _dedupe_by_fact_key(candidates)

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
            fact_key=extras.fact_key,
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
    """Call backend LLM for a one-shot completion and return content via PydanticAI."""
    provider = OpenAIProvider(api_key=api_key or "dummy", base_url=openai_base_url)
    model_cfg = OpenAIModel(model_name=model, provider=provider)
    agent = Agent(
        model=model_cfg,
        system_prompt="",
        instructions=None,
    )
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    result = await agent.run(payload)
    return str(result.output or "")


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
) -> list[FactCandidate]:
    if not user_message and not assistant_message:
        return []
    exchange = []
    if user_message:
        exchange.append(f"User: {user_message}")
    if assistant_message:
        exchange.append(f"Assistant: {assistant_message}")
    transcript = "\n".join(exchange)

    return await _extract_with_pydantic_ai(
        transcript=transcript,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
    )


async def _extract_with_pydantic_ai(
    *,
    transcript: str,
    openai_base_url: str,
    api_key: str | None,
    model: str,
) -> list[FactCandidate]:
    """Use PydanticAI to extract structured facts."""
    provider = OpenAIProvider(
        api_key=api_key or "dummy",
        base_url=openai_base_url,
    )
    model_cfg = OpenAIModel(model_name=model, provider=provider)
    agent = Agent(
        model=model_cfg,
        system_prompt=(
            "You are a memory extractor. From the latest exchange, extract 1-3 succinct facts "
            "that are useful to remember for future turns. Return structured facts with fields: "
            "subject, predicate, object (optional), fact (string), and fact_key (stable identifier). "
            "Do not include prose outside JSON."
        ),
        output_type=list[FactOutput],
        retries=2,
    )
    instructions = (
        "Keep facts atomic, enduring, and person-centered when possible. "
        "Prefer explicit subjects (names) over pronouns. "
        "Avoid formatting; return only JSON."
    )

    try:
        result = await agent.run(transcript, instructions=instructions)
    except Exception:
        logger.exception("PydanticAI fact extraction failed")
        return []

    outputs = result.output or []
    fact_candidates: list[FactCandidate] = []
    for item in outputs:
        content = item.fact or _output_to_text(item)
        key = _ensure_fact_key(item.fact_key, content, item)
        if not content or not key:
            continue
        fact_candidates.append(FactCandidate(content=content, fact_key=key))
    return fact_candidates


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
    sorted_entries = sorted(
        entries,
        key=lambda e: e.metadata.created_at,
    )
    overflow = sorted_entries[:-max_entries]
    delete_entries(collection, [e.id for e in overflow if e.id])


def _latest_user_message(request: ChatRequest) -> str | None:
    """Return the most recent user message, if any."""
    return next((m.content for m in reversed(request.messages) if m.role == "user"), None)


def _assistant_reply_content(response: Mapping[str, Any]) -> str | None:
    """Extract assistant content from a chat completion response."""
    choices = response.get("choices", [])
    if not choices:
        return None
    return choices[0].get("message", {}).get("content")


def _persist_turns(
    collection: Collection,
    *,
    memory_root: Path,
    conversation_id: str,
    user_message: str | None,
    assistant_message: str | None,
) -> None:
    """Persist the latest user/assistant exchanges."""
    _persist_entries(
        collection,
        memory_root=memory_root,
        conversation_id=conversation_id,
        entries=[
            WriteEntry(role="user", content=user_message, extras=MemoryExtras())
            if user_message
            else None,
            WriteEntry(role="assistant", content=assistant_message, extras=MemoryExtras())
            if assistant_message
            else None,
        ],
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
) -> None:
    """Run summarization/fact extraction and eviction."""
    post_start = perf_counter()
    if enable_summarization:
        summary_start = perf_counter()
        await _extract_and_store_facts_and_summaries(
            collection=collection,
            memory_root=memory_root,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
            openai_base_url=openai_base_url,
            api_key=api_key,
            model=model,
        )
        logger.info(
            "Updated facts and summaries in %.1f ms (conversation=%s)",
            _elapsed_ms(summary_start),
            conversation_id,
        )
    eviction_start = perf_counter()
    _evict_if_needed(collection, conversation_id, max_entries)
    logger.info(
        "Eviction check completed in %.1f ms (conversation=%s)",
        _elapsed_ms(eviction_start),
        conversation_id,
    )
    logger.info(
        "Post-processing finished in %.1f ms (conversation=%s, summarization=%s)",
        _elapsed_ms(post_start),
        conversation_id,
        "enabled" if enable_summarization else "disabled",
    )


async def _extract_and_store_facts_and_summaries(
    *,
    collection: Collection,
    memory_root: Path,
    conversation_id: str,
    user_message: str | None,
    assistant_message: str | None,
    openai_base_url: str,
    api_key: str | None,
    model: str,
) -> None:
    """Run fact extraction and summary updates, persisting results."""
    fact_start = perf_counter()
    facts = await _extract_salient_facts(
        user_message=user_message,
        assistant_message=assistant_message,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
    )
    logger.info(
        "Fact extraction produced %d facts in %.1f ms (conversation=%s)",
        len(facts),
        _elapsed_ms(fact_start),
        conversation_id,
    )
    if not facts:
        return

    fact_entries: list[WriteEntry] = [
        WriteEntry(
            role="memory",
            content=fact.content,
            extras=MemoryExtras(
                salience=1.0,
                tags=list(_extract_tags_from_text(fact.content)),
                fact_key=fact.fact_key,
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
    summary_start = perf_counter()
    new_short, new_long = await _update_summaries(
        prior_short=prior_summary,
        prior_long=prior_long,
        new_facts=[fact.content for fact in facts],
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
    )
    logger.info(
        "Summary updates completed in %.1f ms (conversation=%s)",
        _elapsed_ms(summary_start),
        conversation_id,
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
        )
        logger.info(
            "Stream post-processing completed in %.1f ms (conversation=%s)",
            _elapsed_ms(post_start),
            conversation_id,
        )

    async def stream_lines() -> AsyncGenerator[str, None]:
        logger.info(
            "Forwarding streaming chat completion (conversation=%s, model=%s)",
            conversation_id,
            model,
        )
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
            async for line in response.aiter_lines():
                if line:
                    yield line

    async def tee_and_accumulate() -> AsyncGenerator[str, None]:
        assistant_chunks: list[str] = []
        async for line in stream_lines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload != "[DONE]":
                    try:
                        data = json.loads(payload)
                        delta = (data.get("choices") or [{}])[0].get("delta") or {}
                        piece = delta.get("content") or delta.get("text") or ""
                        if piece:
                            assistant_chunks.append(piece)
                    except Exception:
                        logger.debug(
                            "Failed to parse streaming chunk: %s",
                            payload,
                            exc_info=True,
                        )
            yield line + "\n\n"
        assistant_message = "".join(assistant_chunks).strip() or None
        run_in_background(
            _persist_stream_result(assistant_message),
            label=f"stream-postprocess-{conversation_id}",
        )
        logger.info(
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
    tag_boost: float = _DEFAULT_TAG_BOOST,
    postprocess_in_background: bool = True,
) -> Any:
    """Process a chat request with long-term memory support."""
    overall_start = perf_counter()
    retrieval_start = perf_counter()
    aug_request, retrieval, conversation_id = augment_chat_request(
        request,
        collection,
        reranker_model=reranker_model,
        default_top_k=default_top_k,
        mmr_lambda=mmr_lambda,
        tag_boost=tag_boost,
    )
    retrieval_ms = _elapsed_ms(retrieval_start)
    hit_count = len(retrieval.entries) if retrieval else 0
    logger.info(
        "Memory retrieval completed in %.1f ms (conversation=%s, hits=%d, top_k=%d)",
        retrieval_ms,
        conversation_id,
        hit_count,
        request.memory_top_k if request.memory_top_k is not None else default_top_k,
    )

    if request.stream:
        logger.info(
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
        )

    llm_start = perf_counter()
    response = await _forward_request(aug_request, openai_base_url, api_key)
    logger.info(
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
        )

    if postprocess_in_background:
        run_in_background(
            run_postprocess(),
            label=f"postprocess-{conversation_id}",
        )
    else:
        await run_postprocess()

    response["memory_hits"] = (
        [entry.model_dump() for entry in retrieval.entries] if retrieval else []
    )
    logger.info(
        "Request finished in %.1f ms (conversation=%s, hits=%d)",
        _elapsed_ms(overall_start),
        conversation_id,
        hit_count,
    )

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
