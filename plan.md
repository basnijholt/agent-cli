# Memory Server Plan (Self-Hosted, High-Level)

## Goals ✅
- Provide long-term conversational memory that persists salient facts across sessions. ✅
- Rely on self-hostable components: OpenAI-compatible LLM endpoint + local vector store. ✅
- Deliver a familiar `/v1/chat/completions` interface with automatic memory injection. ✅
- Minimize external dependencies while using proven retrieval and summarization patterns. ✅

## Conceptual Architecture ✅
- **Memory store (vector DB)**: Chroma collection keyed by `conversation_id` (plus a “global” scope for cross-conversation facts). Stores atomic memory entries (facts) and summaries with metadata (timestamps, roles, optional tags/salience).
- **Embedding & rerank**: Dense retrieval per conversation (and global) with a cross-encoder reranker for quality; blends relevance with recency/salience for better recall. ✅
- **Summaries**: Rolling summaries per conversation to compress history; always included alongside the most relevant memories. ✅ (short + long)
- **API**: OpenAI-compatible `/v1/chat/completions`; the server augments prompts with memory and forwards to the configured LLM endpoint. ✅

## Retrieval & Prompt Augmentation (High-Level) ✅
1) Identify the latest user message.
2) Retrieve candidate memories for that conversation (and optional global scope) via dense search; rerank with a cross-encoder; mix in recency/salience signals; include the current summary.
3) Construct an augmented user message that embeds the summary and top-k memory snippets before the current question.
4) Forward the augmented request to the backend LLM; stream or return the completion unchanged otherwise.

## Post-Completion Memory Update (High-Level) ✅
1) Persist the raw user/assistant turns to the memory store (scoped by `conversation_id`).
2) Extract a few salient facts from the observed exchange using the LLM (deterministic, short).
3) Upsert those facts as discrete memory entries (embedded for retrieval).
4) Refresh the rolling summary conditioned on the prior summary plus the new facts. ✅ (short + long)
5) Enforce a per-conversation budget (evict oldest/lowest-value entries beyond the cap). ✅

## Ranking & Quality Signals (High-Level) ✅
- **Two-stage retrieval**: dense top-N per scope → cross-encoder rerank → top-k. ✅
- **Hybrid scoring**: combine rerank score with light recency/salience boosts; optional diversity (MMR-style) to avoid near-duplicates. ✅ (MMR lambda configurable)
- **Global scope**: allow a “global” conversation bucket for persona/long-lived facts; merge with per-conversation hits. ✅

## Why This Works (Established Patterns)
- Dense retrieval + cross-encoder rerank is a standard, empirically superior IR pipeline for passage relevance (MS MARCO-era best practice).
- Summaries reduce context bloat while preserving key information; widely used in long-context chat systems.
- Salience extraction keeps stored memories atomic and focused, improving retrieval precision.
- Recency/salience blending improves freshness; diversity reduces redundancy—both are common IR heuristics.

## Configuration (High-Level) ✅
- Memory store path; embedding model/base URL/API key (shared with RAG).
- Retrieval depth (k, pre-rerank N), max entries per conversation, enable/disable summaries. ✅ (plus mmr/tag boosts)
- Backend LLM endpoint/model used for both chat and internal memory prompts. ✅

## File-Backed Persistence ✅
- Source of truth is Markdown files with YAML front matter (id, conversation_id, role, created_at, tags, salience, summary_kind).
- Layout: `<memory_store>/entries/<conversation_slug>/<doc_id>.md`, plus an inspectable JSON snapshot of all records. Summaries and facts are stored via the same path.
- Derived index: Chroma lives under `<memory_store>/chroma`; a watcher re-indexes on file changes so manual edits/additions are reflected automatically. Single entry point (`memory-server`) handles both persistence and retrieval.

## Testing Approach (High-Level)
- Unit checks for scoring, eviction, and parsing utilities. ✅ (basic)
- Integration: spin up the app with a temp vector store and a mock LLM; verify that facts are persisted, retrieved, and summaries are updated. ✅ (mock harness added; live check also done)

## Future Improvements (Ordered by Impact)
1) Conflict-aware fact consolidation: normalize subject/predicate keys, detect overlaps/contradictions, and keep a canonical “active” fact per key (deprecate older ones).
2) Topical clustering + diverse retrieval: cluster facts/events by topic and pick diverse reps per cluster (with recency bias) for better coverage.
3) Hierarchical summaries: add mid-/episodic summaries above the current short/long rolling summaries to stay concise over long chats.
4) Enhanced scoring: blend reranker with adaptive salience, recency decay, tag overlap, and (optionally) a tiny learned combiner; add time-aware boosts.
5) Lifecycle/decay: decay or archive low-value memories; promote high-salience ones into a small “core” set to keep the index clean.
6) Profile/persona separation: keep a structured user profile (immutable traits/preferences) apart from transient conversation facts; allow updates to overwrite profile slots.
7) Perf polish: warm-up calls, batch embeddings, and caches for recent turns/facts; keep postprocessing async.

## Low-Effort Borrowed Ideas from mem0 (short-term)
- Metadata filters/scoping: allow AND/OR and comparison operators plus multi-id scoping (`user_id`/`agent_id`/`run_id`/`actor_id`) to narrow retrieval without extra LLM calls.
- Optional LLM contradiction/diff pass: after retrieving facts by `fact_key`, use a lightweight LLM function-call to propose ADD/UPDATE/DELETE for conflicts; still keep deterministic keys as the final arbiter.
- Provider-flexible hooks: small factories around embeddings/rerankers to swap/back off models without touching core logic.
- Telemetry on memory mutations: emit structured events for add/update/delete to aid debugging and performance tuning.

## Next Up (Immediate Wins, mem0-inspired)
- [x] LLM-driven consolidation pass after retrieval: run a small function-call model over overlapping facts to label ADD/UPDATE/DELETE/KEEP and retire stale/conflicting facts (beyond latest-wins). Implemented via the reconcile prompt/output (mem0-style add/update/delete) and tombstones for deletes.
- [ ] Query rewriting/expansion before retrieval: generate 2–3 disambiguated rewrites/aliases of the user turn, retrieve per rewrite, merge, then rerank. Similar to mem0’s expansion patterns in its memory pipelines (see `mem0/mem0/memory/main.py` retrieval handling).
- [ ] Contradiction/diff check on retrieved facts: focused LLM pass to detect conflicts (e.g., name/location changes) and mark older facts as deprecated. Modeled after mem0’s UPDATE/DELETE logic (`get_update_memory_messages` in `mem0/mem0/configs/prompts.py`).
- [ ] Fact quality gate: lightweight classifier/LLM to drop trivial/banal facts before indexing to keep the store high-signal. Borrow the spirit of mem0’s “facts only” extraction prompts (`USER_MEMORY_EXTRACTION_PROMPT` in `mem0/mem0/configs/prompts.py`), but add a gate step.
- [ ] Summary prompt refinement: tighten rolling short/long summaries using retrieved facts + prior summary; keep outputs concise and reliable. Ensure prompts stay compact; mem0 lacks rolling summaries, so we keep our advantage while hardening prompts.
