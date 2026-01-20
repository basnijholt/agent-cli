"""Retrieval logic for memory (Reading, Reranking, MMR)."""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agent_cli.core.reranker import OnnxCrossEncoder, predict_relevance
from agent_cli.memory._store import get_summary_entry, query_memories
from agent_cli.memory.models import (
    ChatRequest,
    MemoryEntry,
    MemoryMetadata,
    MemoryRetrieval,
    Message,
    StoredMemory,
)

if TYPE_CHECKING:
    from chromadb import Collection

LOGGER = logging.getLogger(__name__)

_DEFAULT_MMR_LAMBDA = 0.7
_SUMMARY_ROLE = "summary"
_MIN_MAX_EPSILON = 1e-8  # Avoid division by zero in min-max normalization


def gather_relevant_existing_memories(
    collection: Collection,
    conversation_id: str,
    new_facts: list[str],
    *,
    neighborhood: int = 5,
) -> list[StoredMemory]:
    """Retrieve a small neighborhood of existing memories per new fact, deduped by id."""
    if not new_facts:
        return []
    filters = [
        {"conversation_id": conversation_id},
        {"role": "memory"},
        {"role": {"$ne": "summary"}},
    ]
    seen: set[str] = set()
    results: list[StoredMemory] = []
    for fact in new_facts:
        raw = collection.query(query_texts=[fact], n_results=neighborhood, where={"$and": filters})
        docs = raw.get("documents", [[]])[0] or []
        metas = raw.get("metadatas", [[]])[0] or []
        ids = raw.get("ids", [[]])[0] or []
        distances = raw.get("distances", [[]])[0] or []
        for doc, meta, doc_id, dist in zip(docs, metas, ids, distances, strict=False):
            assert doc_id is not None
            if doc_id in seen:
                continue
            seen.add(doc_id)
            norm_meta = MemoryMetadata(**dict(meta))
            results.append(
                StoredMemory(
                    id=doc_id,
                    content=doc,
                    metadata=norm_meta,
                    distance=float(dist) if dist is not None else None,
                ),
            )
    return results


def mmr_select(
    candidates: list[StoredMemory],
    scores: list[float],
    *,
    max_items: int,
    lambda_mult: float,
) -> list[tuple[StoredMemory, float]]:
    """Apply Maximal Marginal Relevance to promote diversity."""
    if not candidates or max_items <= 0:
        return []

    def _normalize(vec: list[float] | None) -> list[float] | None:
        if not vec:
            return None
        norm = sum(x * x for x in vec) ** 0.5
        if norm == 0:
            return None
        return [x / norm for x in vec]

    def _cosine(a: list[float] | None, b: list[float] | None) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        return sum(x * y for x, y in zip(a, b, strict=False))

    normalized_embeddings: list[list[float] | None] = [
        _normalize(mem.embedding) for mem in candidates
    ]

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
                (_cosine(normalized_embeddings[idx], normalized_embeddings[s]) for s in selected),
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


def retrieve_memory(
    collection: Collection,
    *,
    conversation_id: str,
    query: str,
    top_k: int,
    reranker_model: OnnxCrossEncoder,
    include_global: bool = True,
    include_summary: bool = True,
    mmr_lambda: float = _DEFAULT_MMR_LAMBDA,
    recency_weight: float = 0.2,
    score_threshold: float | None = None,
    filters: dict[str, Any] | None = None,
) -> tuple[MemoryRetrieval, list[str]]:
    """Execute search + rerank + recency + MMR."""
    candidate_conversations = [conversation_id]
    if include_global and conversation_id != "global":
        candidate_conversations.append("global")

    raw_candidates: list[StoredMemory] = []
    seen_ids: set[str] = set()

    for cid in candidate_conversations:
        records = query_memories(
            collection,
            conversation_id=cid,
            text=query,
            n_results=top_k * 3,
            filters=filters,
        )
        for rec in records:
            rec_id = rec.id
            if rec_id in seen_ids:
                continue
            seen_ids.add(rec_id)
            raw_candidates.append(rec)

    def _min_max_normalize(scores: list[float]) -> list[float]:
        """Normalize scores to 0-1 range using min-max scaling."""
        if not scores:
            return scores
        min_score = min(scores)
        max_score = max(scores)
        if max_score - min_score < _MIN_MAX_EPSILON:
            return [0.5] * len(scores)  # All scores equal
        return [(s - min_score) / (max_score - min_score) for s in scores]

    def recency_score(meta: MemoryMetadata) -> float:
        dt = datetime.fromisoformat(meta.created_at)
        age_days = max((datetime.now(UTC) - dt).total_seconds() / 86400.0, 0.0)
        # Exponential decay: ~0.36 score at 30 days
        return math.exp(-age_days / 30.0)

    final_candidates: list[StoredMemory] = []
    scores: list[float] = []

    if raw_candidates:
        pairs = [(query, mem.content) for mem in raw_candidates]
        rr_scores = predict_relevance(reranker_model, pairs)
        # Normalize raw reranker scores to 0-1 range
        normalized_scores = _min_max_normalize(rr_scores)

        for mem, relevance in zip(raw_candidates, normalized_scores, strict=False):
            # Filter out low-relevance memories if threshold is set
            if score_threshold is not None and relevance < score_threshold:
                continue

            recency = recency_score(mem.metadata)
            # Weighted blend
            total = (1.0 - recency_weight) * relevance + recency_weight * recency
            scores.append(total)
            final_candidates.append(mem)

    selected = mmr_select(final_candidates, scores, max_items=top_k, lambda_mult=mmr_lambda)

    entries: list[MemoryEntry] = [
        MemoryEntry(
            role=mem.metadata.role,
            content=mem.content,
            created_at=mem.metadata.created_at,
            score=score,
        )
        for mem, score in selected
    ]

    summaries: list[str] = []
    if include_summary:
        summary_entry = get_summary_entry(collection, conversation_id, role=_SUMMARY_ROLE)
        if summary_entry:
            summaries.append(f"Conversation summary:\n{summary_entry.content}")

    return MemoryRetrieval(entries=entries), summaries


def format_augmented_content(
    *,
    user_message: str,
    summaries: list[str],
    memories: list[MemoryEntry],
) -> str:
    """Format the prompt content with injected memories."""
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
    default_top_k: int = 5,
    default_memory_id: str = "default",
    include_global: bool = True,
    mmr_lambda: float = _DEFAULT_MMR_LAMBDA,
    recency_weight: float = 0.2,
    score_threshold: float | None = None,
    filters: dict[str, Any] | None = None,
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
        LOGGER.info("Memory retrieval disabled for this request (top_k=%s)", top_k)
        return request, None, conversation_id, []

    retrieval, summaries = retrieve_memory(
        collection,
        conversation_id=conversation_id,
        query=user_message,
        top_k=top_k,
        reranker_model=reranker_model,
        include_global=include_global,
        mmr_lambda=mmr_lambda,
        recency_weight=recency_weight,
        score_threshold=score_threshold,
        filters=filters,
    )

    if not retrieval.entries and not summaries:
        return request, None, conversation_id, summaries

    augmented_content = format_augmented_content(
        user_message=user_message,
        summaries=summaries,
        memories=retrieval.entries,
    )

    augmented_messages = list(request.messages[:-1])
    augmented_messages.append(Message(role="user", content=augmented_content))

    aug_request = request.model_copy()
    aug_request.messages = augmented_messages

    return aug_request, retrieval, conversation_id, summaries
