"""Core memory engine logic."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi.responses import StreamingResponse
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from agent_cli.core.openai_proxy import forward_chat_request
from agent_cli.memory import streaming
from agent_cli.memory.files import ensure_store_dirs, read_memory_file, write_memory_file
from agent_cli.memory.models import (
    ChatRequest,
    ConsolidationDecision,
    MemoryEntry,
    MemoryMetadata,
    MemoryRetrieval,
    MemoryUpdateDecision,
    Message,
    StoredMemory,
    SummaryOutput,
)
from agent_cli.memory.prompt import (
    CONSOLIDATION_PROMPT,
    CONTRADICTION_PROMPT,
    FACT_INSTRUCTIONS,
    FACT_SYSTEM_PROMPT,
    QUERY_REWRITE_PROMPT,
    SUMMARY_PROMPT,
    UPDATE_MEMORY_PROMPT,
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
_SUMMARY_SHORT_ROLE = "summary_short"
_SUMMARY_LONG_ROLE = "summary_long"
_DEFAULT_MAX_REWRITES = 2


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


@dataclass
class PersistEntry:
    """Structured memory entry to persist."""

    role: str
    content: str
    salience: float | None = None


async def _consolidate_retrieval_entries(
    entries: list[MemoryEntry],
    *,
    openai_base_url: str,
    api_key: str | None,
    model: str,
    prompt: str = CONSOLIDATION_PROMPT,
) -> list[MemoryEntry]:
    """Use a small LLM pass to mark overlapping facts to KEEP/DELETE/UPDATE."""
    if len(entries) <= 1:
        return entries

    provider = OpenAIProvider(
        api_key=api_key or "dummy",
        base_url=openai_base_url,
    )
    model_cfg = OpenAIChatModel(
        model_name=model,
        provider=provider,
        settings=ModelSettings(temperature=0.0, max_tokens=256),
    )
    agent = Agent(
        model=model_cfg,
        system_prompt=prompt,
        output_type=list[ConsolidationDecision],
        retries=1,
    )

    payload_lines = [
        f"{idx}. [created_at={entry.created_at}] {entry.content}"
        for idx, entry in enumerate(entries)
    ]
    payload = "\n".join(payload_lines)
    try:
        result = await agent.run(payload)
        decisions = {d.id: d.action for d in result.output}
    except Exception:
        logger.exception("Consolidation agent failed; keeping all retrieved entries")
        return entries

    if not decisions:
        return entries

    kept: list[MemoryEntry] = []
    for idx, entry in enumerate(entries):
        action = decisions.get(str(idx))
        if action in ("KEEP", "UPDATE"):
            kept.append(entry)

    return kept or entries


def _prepare_fact_entries(facts: list[str]) -> list[PersistEntry]:
    """Convert extracted fact strings into persistable entries."""
    entries: list[PersistEntry] = []
    for text in facts:
        cleaned = (text or "").strip()
        if not cleaned:
            continue
        entries.append(
            PersistEntry(
                role="memory",
                content=cleaned,
                salience=1.0,
            ),
        )
    logger.info("Prepared %d fact entries: %s", len(entries), [e.content for e in entries])
    return entries


def _gather_relevant_existing_memories(
    collection: Collection,
    conversation_id: str,
    new_facts: list[str],
    *,
    neighborhood: int = 5,
) -> list[StoredMemory]:
    """Retrieve a small neighborhood of existing memories per new fact, deduped by id.

    Note: Only true memory facts (role == "memory") are considered here. Turns
    are excluded to avoid blocking fact insertion when the only stored content
    is raw conversation turns.
    """
    if not new_facts:
        return []
    filters = [
        {"conversation_id": conversation_id},
        {"role": "memory"},
        {"role": {"$ne": "summary_short"}},
        {"role": {"$ne": "summary_long"}},
    ]
    seen: set[str] = set()
    results: list[StoredMemory] = []
    for fact in new_facts:
        raw = collection.query(
            query_texts=[fact],
            n_results=neighborhood,
            where={"$and": filters},
        )
        docs = raw.get("documents", [[]])[0] or []
        metas = raw.get("metadatas", [[]])[0] or []
        ids = raw.get("ids", [[]])[0] or []
        distances = raw.get("distances", [[]])[0] or []
        for doc, meta, doc_id, dist in zip(docs, metas, ids, distances, strict=False):
            if doc_id is None or doc_id in seen:
                continue
            seen.add(doc_id)
            norm_meta = MemoryMetadata(**dict(meta))
            results.append(
                StoredMemory(
                    id=str(doc_id),
                    content=str(doc),
                    metadata=norm_meta,
                    distance=float(dist) if dist is not None else None,
                ),
            )
    return results


def _delete_fact_files(memory_root: Path, conversation_id: str, ids: list[str]) -> None:
    """Tombstone fact markdown files matching the given ids."""
    if not ids:
        return
    entries_dir, _ = ensure_store_dirs(memory_root)
    conv_dir = entries_dir / _safe_identifier(conversation_id)
    facts_dir = conv_dir / "facts"
    deleted_dir = conv_dir / "deleted" / "facts"
    deleted_dir.mkdir(parents=True, exist_ok=True)
    if not facts_dir.exists():
        return
    for path in facts_dir.glob("*.md"):
        rec = read_memory_file(path)
        if rec and rec.id in ids:
            try:
                path.rename(deleted_dir / path.name)
            except Exception:
                logger.exception("Failed to tombstone fact file %s", path)


async def _rewrite_queries(
    user_message: str,
    *,
    openai_base_url: str,
    api_key: str | None,
    model: str,
    max_rewrites: int = _DEFAULT_MAX_REWRITES,
) -> list[str]:
    """Generate a small set of disambiguated rewrites to improve recall."""
    provider = OpenAIProvider(
        api_key=api_key or "dummy",
        base_url=openai_base_url,
    )
    model_cfg = OpenAIChatModel(
        model_name=model,
        provider=provider,
        settings=ModelSettings(temperature=0.2, max_tokens=128),
    )
    agent = Agent(
        model=model_cfg,
        system_prompt=QUERY_REWRITE_PROMPT,
        output_type=list[str],
        retries=1,
    )
    try:
        result = await agent.run(user_message)
        rewrites = result.output or []
    except Exception:
        logger.exception("Query rewrite agent failed; using original message only")
        rewrites = []

    unique: list[str] = []
    for candidate in [user_message, *rewrites]:
        if candidate and candidate not in unique:
            unique.append(candidate)
        if len(unique) >= max_rewrites + 1:  # include original + max_rewrites
            break
    return unique or [user_message]


def _retrieve_memory(
    collection: Collection,
    *,
    conversation_id: str,
    queries: list[str],
    top_k: int,
    reranker_model: OnnxCrossEncoder,
    include_global: bool = True,
    include_summary: bool = True,
    mmr_lambda: float = _DEFAULT_MMR_LAMBDA,
) -> tuple[MemoryRetrieval, list[str]]:
    candidate_conversations = [conversation_id]
    if include_global and conversation_id != "global":
        candidate_conversations.append("global")

    candidates: list[StoredMemory] = []
    seen_ids: set[str] = set()
    for q in queries:
        for cid in candidate_conversations:
            records = query_memories(
                collection,
                conversation_id=cid,
                text=q,
                n_results=top_k * 3,
            )
            for rec in records:
                rec_id = rec.id
                if rec_id in seen_ids:
                    continue
                seen_ids.add(rec_id)
                candidates.append(rec)

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

    scores: list[float] = []
    if candidates:
        primary_query = queries[0] if queries else ""
        pairs = [(primary_query, mem.content) for mem in candidates]
        rr_scores = predict_relevance(reranker_model, pairs)
        for mem, rr in zip(candidates, rr_scores, strict=False):
            base = rr
            dist_bonus = 0.0 if mem.distance is None else 1.0 / (1.0 + mem.distance)
            total = (
                base
                + 0.1 * dist_bonus
                + 0.2 * recency_boost(mem.metadata)
                + 0.1 * salience_boost(mem.metadata)
            )
            scores.append(total)
    else:
        for mem in candidates:
            base = 0.0 if mem.distance is None else 1.0 / (1.0 + mem.distance)
            total = base + 0.2 * recency_boost(mem.metadata) + 0.1 * salience_boost(mem.metadata)
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


async def augment_chat_request(
    request: ChatRequest,
    collection: Collection,
    reranker_model: OnnxCrossEncoder,
    openai_base_url: str,
    api_key: str | None,
    default_top_k: int = 5,
    default_memory_id: str = "default",
    include_global: bool = True,
    mmr_lambda: float = _DEFAULT_MMR_LAMBDA,
) -> tuple[ChatRequest, MemoryRetrieval | None, str, list[str]]:
    """Retrieve memory context and augment the chat request."""
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        None,
    )
    if not user_message:
        return request, None, default_memory_id, []

    conversation_id = request.memory_id or default_memory_id
    top_k = request.memory_top_k if request.memory_top_k is not None else default_top_k

    if top_k <= 0:
        logger.info("Memory retrieval disabled for this request (top_k=%s)", top_k)
        return request, None, conversation_id, []

    rewrites = await _rewrite_queries(
        user_message,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=request.model,
    )

    retrieval, summaries = _retrieve_memory(
        collection,
        conversation_id=conversation_id,
        queries=rewrites,
        top_k=top_k,
        reranker_model=reranker_model,
        include_global=include_global,
        mmr_lambda=mmr_lambda,
    )

    if not retrieval.entries and not summaries:
        return request, None, conversation_id, summaries

    if len(retrieval.entries) > 1:
        # Consolidate overlapping/contradictory facts before building the prompt.
        consolidated = await _consolidate_retrieval_entries(
            retrieval.entries,
            openai_base_url=openai_base_url,
            api_key=api_key,
            model=request.model,
            prompt=CONTRADICTION_PROMPT,
        )
        retrieval = MemoryRetrieval(entries=consolidated)

    augmented_content = _format_augmented_content(
        user_message=user_message,
        summaries=summaries,
        memories=retrieval.entries,
    )

    augmented_messages = list(request.messages[:-1])
    augmented_messages.append(Message(role="user", content=augmented_content))

    aug_request = request.model_copy()
    aug_request.messages = augmented_messages

    return aug_request, retrieval, conversation_id, summaries


def _persist_entries(
    collection: Collection,
    *,
    memory_root: Path,
    conversation_id: str,
    entries: list[PersistEntry | None],
) -> None:
    now = datetime.now(UTC).isoformat()
    ids: list[str] = []
    contents: list[str] = []
    metadatas: list[MemoryMetadata] = []
    for item in entries:
        if item is None:
            continue
        role, content, salience = item.role, item.content, item.salience
        record = write_memory_file(
            memory_root,
            conversation_id=conversation_id,
            role=role,
            created_at=now,
            content=content,
            salience=salience,
            doc_id=str(uuid4()),
        )
        ids.append(record.id)
        contents.append(record.content)
        metadatas.append(record.metadata)
    if ids:
        upsert_memories(collection, ids=ids, contents=contents, metadatas=metadatas)


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

    # Extract facts from the latest user turn only (ignore assistant/system).
    transcript = user_message or ""

    facts = await _extract_with_pydantic_ai(
        transcript=transcript,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
    )
    logger.info("Raw fact extraction output: %s", facts)
    return facts


async def _reconcile_facts(
    collection: Collection,
    conversation_id: str,
    new_facts: list[str],
    *,
    openai_base_url: str,
    api_key: str | None,
    model: str,
) -> tuple[list[str], list[str]]:
    """Use an LLM to decide add/update/delete/none for facts, with id remapping."""
    if not new_facts:
        return [], []

    existing = _gather_relevant_existing_memories(collection, conversation_id, new_facts)
    if not existing:
        logger.info("Reconcile: no existing memory facts; defaulting to add all new facts")
        return new_facts, []
    id_map: dict[str, str] = {str(idx): mem.id for idx, mem in enumerate(existing)}
    existing_json = [
        {"id": short_id, "text": mem.content}
        for short_id, mem in zip(id_map.keys(), existing, strict=False)
    ]

    provider = OpenAIProvider(api_key=api_key or "dummy", base_url=openai_base_url)
    model_cfg = OpenAIChatModel(
        model_name=model,
        provider=provider,
        settings=ModelSettings(temperature=0.0, max_tokens=512),
    )
    agent = Agent(
        model=model_cfg,
        system_prompt=UPDATE_MEMORY_PROMPT,
        output_type=list[MemoryUpdateDecision],
        retries=1,
    )

    payload_obj = {"existing": existing_json, "new_facts": new_facts}
    payload = json.dumps(payload_obj, ensure_ascii=False, indent=2)
    logger.info("Reconcile payload JSON: %s", payload)
    try:
        result = await agent.run(payload)
        decisions = result.output or []
    except Exception:
        logger.exception("Update memory agent failed; defaulting to add all new facts")
        return new_facts, []

    to_add: list[str] = []
    to_delete: list[str] = []
    for dec in decisions:
        if dec.event == "ADD" and dec.text:
            to_add.append(dec.text.strip())
        elif dec.event == "UPDATE" and dec.id and dec.text:
            orig = id_map.get(dec.id)
            if orig:
                to_delete.append(orig)
                to_add.append(dec.text.strip())
        elif dec.event == "DELETE" and dec.id:
            orig = id_map.get(dec.id)
            if orig:
                to_delete.append(orig)
        # NONE ignored

    # Safeguard: if the model produced no additions and the new facts would otherwise be lost,
    # retain the new facts. This prevents ending up with an empty fact set after deletes.
    if not to_add and new_facts:
        logger.info("Reconcile produced no additions; retaining new facts to avoid empty store")
        to_add = list(new_facts)

    logger.info(
        "Reconcile decisions: add=%d, delete=%d, events=%s",
        len(to_add),
        len(to_delete),
        [dec.event for dec in decisions],
    )
    return to_add, to_delete


async def _extract_with_pydantic_ai(
    *,
    transcript: str,
    openai_base_url: str,
    api_key: str | None,
    model: str,
) -> list[str]:
    """Use PydanticAI to extract fact strings."""
    provider = OpenAIProvider(
        api_key=api_key or "dummy",
        base_url=openai_base_url,
    )
    model_cfg = OpenAIChatModel(model_name=model, provider=provider)
    agent = Agent(
        model=model_cfg,
        system_prompt=FACT_SYSTEM_PROMPT,
        output_type=list[str],
        retries=2,
    )
    instructions = FACT_INSTRUCTIONS

    try:
        facts = await agent.run(transcript, instructions=instructions)
        return facts.output
    except Exception:
        logger.exception("PydanticAI fact extraction failed")
        return []


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
    system_prompt = SUMMARY_PROMPT
    user_parts = []
    if prior_summary:
        user_parts.append(f"Previous summary:\n{prior_summary}")
    user_parts.append("New facts:\n" + "\n".join(f"- {fact}" for fact in new_facts))
    prompt_text = "\n\n".join(user_parts)
    provider = OpenAIProvider(api_key=api_key or "dummy", base_url=openai_base_url)
    model_cfg = OpenAIChatModel(
        model_name=model,
        provider=provider,
        settings=ModelSettings(temperature=0.2, max_tokens=max_tokens),
    )
    agent = Agent(model=model_cfg, system_prompt=system_prompt, output_type=SummaryOutput)
    result = await agent.run(prompt_text)
    summary = result.output.summary if result.output else None
    return summary or prior_summary


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
            PersistEntry(role="user", content=user_message) if user_message else None,
            PersistEntry(role="assistant", content=assistant_message)
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
    to_add, to_delete = await _reconcile_facts(
        collection,
        conversation_id,
        facts,
        openai_base_url=openai_base_url,
        api_key=api_key,
        model=model,
    )

    if to_delete:
        delete_entries(collection, ids=list(to_delete))
        _delete_fact_files(memory_root, conversation_id, list(to_delete))

    fact_entries = _prepare_fact_entries(to_add)

    if not fact_entries:
        return

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
        new_facts=facts,
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

    async def tee_and_accumulate() -> AsyncGenerator[str, None]:
        assistant_chunks: list[str] = []
        async for line in streaming.stream_chat_sse(
            openai_base_url=openai_base_url,
            payload=forward_payload,
            headers=headers,
        ):
            streaming.accumulate_assistant_text(line, assistant_chunks)
            yield line + "\n\n"
        assistant_message = "".join(assistant_chunks).strip() or None
        if assistant_message:
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
    postprocess_in_background: bool = True,
) -> Any:
    """Process a chat request with long-term memory support."""
    overall_start = perf_counter()
    retrieval_start = perf_counter()
    aug_request, retrieval, conversation_id, _summaries = await augment_chat_request(
        request,
        collection,
        reranker_model=reranker_model,
        openai_base_url=openai_base_url,
        api_key=api_key,
        default_top_k=default_top_k,
        include_global=True,
        mmr_lambda=mmr_lambda,
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
        run_in_background(run_postprocess(), label=f"postprocess-{conversation_id}")
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
