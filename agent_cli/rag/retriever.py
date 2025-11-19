"""RAG Retrieval Logic (Functional)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sentence_transformers import CrossEncoder

from agent_cli.rag.models import RagSource, RetrievalResult
from agent_cli.rag.store import query_docs

if TYPE_CHECKING:
    from chromadb import Collection

logger = logging.getLogger("agent_cli.rag.retriever")


def get_reranker_model(
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> CrossEncoder:
    """Load the CrossEncoder model."""
    return CrossEncoder(model_name)


def predict_relevance(
    model: CrossEncoder,
    pairs: list[tuple[str, str]],
) -> list[float]:
    """Predict relevance scores for query-document pairs."""
    return model.predict(pairs, show_progress_bar=False).tolist()  # type: ignore[no-any-return]


def search_context(
    collection: Collection,
    reranker_model: CrossEncoder,
    query: str,
    top_k: int = 3,
) -> RetrievalResult:
    """Retrieve relevant context for a query using hybrid search."""
    try:
        # Initial retrieval - fetch more candidates for reranking
        # Fetch 3x requested docs to have a good pool for reranking
        n_candidates = top_k * 3
        results = query_docs(collection, query, n_results=n_candidates)

        if not results["documents"] or not results["documents"][0]:
            return RetrievalResult(context="", sources=[])

        # Prepare for reranking
        docs = results["documents"][0]
        metas = results["metadatas"][0]  # type: ignore[index]

        # Rerank
        pairs = [(query, doc) for doc in docs]
        scores = predict_relevance(reranker_model, pairs)

        # Sort and take top_k
        ranked = sorted(
            zip(docs, metas, scores, strict=False),
            key=lambda x: x[2],
            reverse=True,
        )[:top_k]

        context = "\n\n---\n\n".join(doc for doc, _, _ in ranked)
        sources = [
            RagSource(
                source=str(meta.get("source", "unknown")),
                path=str(meta.get("file_path", "unknown")),
                chunk_id=int(meta.get("chunk_id", 0)),
                score=float(score),
            )
            for _, meta, score in ranked
        ]

        return RetrievalResult(context=context, sources=sources)

    except Exception:
        logger.exception("Retrieval error")
        return RetrievalResult(context="", sources=[])
