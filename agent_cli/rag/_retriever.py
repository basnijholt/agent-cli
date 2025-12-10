"""RAG Retrieval Logic (Functional)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_cli.core.reranker import OnnxCrossEncoder, predict_relevance
from agent_cli.rag._store import query_docs
from agent_cli.rag.models import RagSource, RetrievalResult

if TYPE_CHECKING:
    from chromadb import Collection

LOGGER = logging.getLogger(__name__)


def format_context(
    ranked: list[tuple[str, dict, float]],
    source_key: str = "source",
    path_key: str = "file_path",
    chunk_key: str = "chunk_id",
) -> str:
    """Format ranked documents as XML for context injection.

    Args:
        ranked: List of (doc, meta, score) tuples from rerank_and_filter().
        source_key: Metadata key for source name.
        path_key: Metadata key for file path.
        chunk_key: Metadata key for chunk ID.

    Returns:
        XML-formatted context string.

    """
    if not ranked:
        return ""

    context_parts = []
    for i, (doc, meta, score) in enumerate(ranked):
        source = meta.get(source_key, "unknown")
        path = meta.get(path_key, meta.get("doc_id", "unknown"))
        chunk = meta.get(chunk_key, 0)
        context_parts.append(
            f'<document index="{i + 1}" source="{source}" '
            f'path="{path}" chunk="{chunk}" score="{score:.3f}">\n{doc}\n</document>',
        )

    return "\n".join(context_parts)


def rerank_and_filter(
    reranker: OnnxCrossEncoder,
    query: str,
    docs: list[str],
    metas: list[dict],
    top_k: int,
    min_score: float = 0.2,
) -> list[tuple[str, dict, float]]:
    """Rerank documents and filter by minimum score.

    Args:
        reranker: Cross-encoder model for reranking.
        query: Search query string.
        docs: List of document texts.
        metas: List of metadata dicts corresponding to docs.
        top_k: Maximum number of results to return.
        min_score: Minimum relevance score threshold.

    Returns:
        List of (doc, meta, score) tuples, sorted by score descending.

    """
    if not docs:
        return []

    # Rerank
    pairs = [(query, doc) for doc in docs]
    scores = predict_relevance(reranker, pairs)

    # Sort by score descending
    ranked_all = sorted(
        zip(docs, metas, scores, strict=False),
        key=lambda x: x[2],
        reverse=True,
    )

    # Filter by min_score and take top_k
    ranked = [(d, m, s) for d, m, s in ranked_all if s >= min_score][:top_k]

    # Log retrieval quality
    filtered_count = len(ranked_all) - len([x for x in ranked_all if x[2] >= min_score])
    top_score = ranked_all[0][2] if ranked_all else 0.0
    LOGGER.info(
        "Retrieval: query_len=%d, candidates=%d, returned=%d, "
        "top_score=%.3f, min_score=%.3f, filtered=%d",
        len(query),
        len(docs),
        len(ranked),
        top_score,
        min_score,
        filtered_count,
    )

    return ranked


def search_context(
    collection: Collection,
    reranker_model: OnnxCrossEncoder,
    query: str,
    top_k: int = 3,
    min_score: float = 0.2,
) -> RetrievalResult:
    """Retrieve relevant context for a query using hybrid search.

    Args:
        collection: ChromaDB collection to search.
        reranker_model: Cross-encoder model for reranking.
        query: Search query string.
        top_k: Maximum number of results to return.
        min_score: Minimum relevance score threshold. Results below this are filtered out.

    Returns:
        RetrievalResult with context and sources. Empty if no results meet min_score.

    """
    # Initial retrieval - fetch more candidates for reranking
    n_candidates = top_k * 3
    results = query_docs(collection, query, n_results=n_candidates)

    if not results["documents"] or not results["documents"][0]:
        return RetrievalResult(context="", sources=[])

    docs = results["documents"][0]
    metas = results["metadatas"][0]  # type: ignore[index]

    # Rerank and filter
    ranked = rerank_and_filter(reranker_model, query, docs, metas, top_k, min_score)

    if not ranked:
        return RetrievalResult(context="", sources=[])

    # Build context and sources
    context = format_context(ranked)
    sources = [
        RagSource(
            source=meta["source"],
            path=meta["file_path"],
            chunk_id=meta["chunk_id"],
            score=float(score),
        )
        for _, meta, score in ranked
    ]

    return RetrievalResult(context=context, sources=sources)
