# Memory Server Plan (Self-Hosted, High-Level)

## Goals
- Provide long-term conversational memory that persists salient facts across sessions.
- Rely on self-hostable components: OpenAI-compatible LLM endpoint + local vector store.
- Deliver a familiar `/v1/chat/completions` interface with automatic memory injection.
- Minimize external dependencies while using proven retrieval and summarization patterns.

## Conceptual Architecture
- **Memory store (vector DB)**: Chroma collection keyed by `conversation_id` (plus a “global” scope for cross-conversation facts). Stores atomic memory entries (facts) and summaries with metadata (timestamps, roles, optional tags/salience).
- **Embedding & rerank**: Dense retrieval per conversation (and global) with a cross-encoder reranker for quality; blends relevance with recency/salience for better recall.
- **Summaries**: Rolling summaries per conversation to compress history; always included alongside the most relevant memories.
- **API**: OpenAI-compatible `/v1/chat/completions`; the server augments prompts with memory and forwards to the configured LLM endpoint.

## Retrieval & Prompt Augmentation (High-Level)
1) Identify the latest user message.
2) Retrieve candidate memories for that conversation (and optional global scope) via dense search; rerank with a cross-encoder; mix in recency/salience signals; include the current summary.
3) Construct an augmented user message that embeds the summary and top-k memory snippets before the current question.
4) Forward the augmented request to the backend LLM; stream or return the completion unchanged otherwise.

## Post-Completion Memory Update (High-Level)
1) Persist the raw user/assistant turns to the memory store (scoped by `conversation_id`).
2) Extract a few salient facts from the observed exchange using the LLM (deterministic, short).
3) Upsert those facts as discrete memory entries (embedded for retrieval).
4) Refresh the rolling summary conditioned on the prior summary plus the new facts.
5) Enforce a per-conversation budget (evict oldest/lowest-value entries beyond the cap).

## Ranking & Quality Signals (High-Level)
- **Two-stage retrieval**: dense top-N per scope → cross-encoder rerank → top-k.
- **Hybrid scoring**: combine rerank score with light recency/salience boosts; optional diversity (MMR-style) to avoid near-duplicates.
- **Global scope**: allow a “global” conversation bucket for persona/long-lived facts; merge with per-conversation hits.

## Why This Works (Established Patterns)
- Dense retrieval + cross-encoder rerank is a standard, empirically superior IR pipeline for passage relevance (MS MARCO-era best practice).
- Summaries reduce context bloat while preserving key information; widely used in long-context chat systems.
- Salience extraction keeps stored memories atomic and focused, improving retrieval precision.
- Recency/salience blending improves freshness; diversity reduces redundancy—both are common IR heuristics.

## Configuration (High-Level)
- Memory store path; embedding model/base URL/API key (shared with RAG).
- Retrieval depth (k, pre-rerank N), max entries per conversation, enable/disable summaries.
- Backend LLM endpoint/model used for both chat and internal memory prompts.

## Testing Approach (High-Level)
- Unit checks for scoring, eviction, and parsing utilities.
- Integration: spin up the app with a temp vector store and a mock LLM; verify that facts are persisted, retrieved, and summaries are updated.
