# Memory System Overview (Current Implementation)

This document captures what the agent_cli memory system does today so we can research alternatives and improvements. It summarizes the architecture, retrieval/ranking math, prompts, observed behavior, issues, and open questions to drive a deeper literature review on memory/RAG strategies.

## What this is for
- Reference for evaluating design choices (rerank + MMR + boosts) against research/industry practices.
- Checklist of known gaps and questions to answer with papers/benchmarks.
- Context for why we built it this way: we want a self-hostable memory layer that automatically persists conversation turns, extracts facts, and injects relevant memories into chat completions via an OpenAI-compatible proxy, using dense retrieval + rerank + light diversity/recency signals.

## One-paragraph overview (for new readers)
We run a self-hostable memory service that ingests chat turns (and optionally external docs), extracts facts, and stores everything in a Chroma vector DB. At query time we take the latest user message, optionally rewrite it, retrieve dense candidates from Chroma, rerank them with a cross-encoder, add small distance/recency boosts, and apply MMR on embedding cosine to keep the final top-k diverse. We then inject those memories (plus summaries) into the chat request and forward it to an OpenAI-compatible LLM. Summaries and fact reconciliation are LLM-driven; persistence uses Markdown + Chroma; all model calls go through an OpenAI-compatible endpoint.

## Architecture & Data Flow (Current Implementation)

### 1. Main Components

**Runtime service**

* **FastAPI app (`agent_cli.memory.api`)**
  * `POST /v1/chat/completions`
    * Accepts an OpenAI-style chat request plus `memory_id` / `memory_top_k`.
    * Extracts bearer token from `Authorization` and passes it through as the chat API key.
    * Delegates to `MemoryClient.chat(...)`.
  * `GET /health` returns basic config (memory path, base URL, top-k).
  * Startup/shutdown events start/stop a background file watcher.

* **MemoryClient (`agent_cli.memory.client.MemoryClient`)**
  * Owns:
    * `memory_path`: root dir for Markdown + Chroma.
    * `collection`: Chroma collection initialized via `init_memory_collection`.
    * `index`: in-memory index of Markdown files (`MemoryIndex`).
    * `reranker_model`: ONNX cross-encoder (via `get_reranker_model()`).
    * Config: `embedding_model` (default `text-embedding-3-small`), `default_top_k`, `max_entries`, `mmr_lambda`, `enable_summarization`.
  * Public methods:
    * `chat(...)`: full memory-augmented chat.
    * `search(...)`: retrieve relevant memories for a query.
    * `add(...)`: add memories from arbitrary text (fact extraction + reconciliation).

**Storage**

* **File store (`agent_cli.memory.files`)**
  * Source of truth is **Markdown files with YAML front matter** under:
    * `<memory_path>/entries/<conversation_id>/...`
  * Layout (by role):
    * `turns/user/<timestamp>__<id>.md`
    * `turns/assistant/<timestamp>__<id>.md`
    * `facts/<timestamp>__<id>.md`
    * `summaries/short.md` (role `summary_short`)
    * `summaries/long.md` (role `summary_long`)
  * Each file has:
    * Front matter: `id`, `conversation_id`, `role`, `created_at`, optional `summary_kind`.
    * Body: plain text content.

* **Vector store (`agent_cli.memory.store`)**
  * One Chroma collection per memory root (default name `"memory"`, stored under `<memory_path>/chroma`).
  * All conversations share this collection and are keyed by `metadata.conversation_id`.
  * Helpers:
    * `upsert_memories(...)`: wraps Chroma upsert.
    * `query_memories(...)`: dense retrieval with embeddings (`include=["embeddings"]`).
    * `get_summary_entry(...)`: fetches the (single) summary doc for a conversation and role.
    * `list_conversation_entries(...)`: list all entries for a conversation (optionally filtering summaries).
    * `delete_entries(...)`: delete by IDs.

**Indexer / watcher**

* **MemoryIndex + watch (`agent_cli.memory.indexer`)**
  * `MemoryIndex` keeps a map `{id -> MemoryFileRecord}` plus a JSON snapshot (`memory_index.json`) on disk.
  * `initial_index(...)`:
    * Loads all Markdown files (`load_memory_files`).
    * Compares with snapshot:
      * Deletes stale docs from Chroma.
      * (Re)upserts all current docs to Chroma.
    * Rewrites snapshot with the current set.
  * `watch_memory_store(...)`:
    * Uses `watch_directory` (from `agent_cli.core.watch`) to monitor `<memory_path>/entries`.
    * On file changes:
      * `Change.deleted`: deletes from Chroma and from index.
      * `Change.added` / `Change.modified`: re-reads file, upserts to Chroma, updates index.

**LLM and reranker**

* **LLM / OpenAI-compatible endpoint**
  * All model calls (chat, fact extraction, summarization, query rewrite, reconciliation) go through an OpenAI-compatible base URL:
    * Chat and fact/summarization prompts use `pydantic_ai` with `OpenAIProvider`.
    * Chat completions are proxied via `forward_chat_request` or `stream_chat_sse`.

* **Cross-encoder reranker (`agent_cli.rag.retriever`)**
  * Loaded once per `MemoryClient` (`get_reranker_model()`).
  * Used in `_retrieve_memory` to score `(query, doc)` pairs.

### 2. Request Flow: Chat With Memory

**Entry point (API → client)**
1. Client calls `POST /v1/chat/completions` with:
   * `messages` (OpenAI format)
   * `model`
   * Optional: `memory_id`, `memory_top_k`, `stream`.
2. `MemoryClient.chat` wraps this into a `ChatRequest` (Pydantic model) and calls:
   ```python
   process_chat_request(...)
   ```

**Step 1: Augment request with memory (`augment_chat_request`)**
1. Identify **latest user message** (`_latest_user_message`).
2. Determine:
   * `conversation_id = request.memory_id or "default"`.
   * `top_k = request.memory_top_k or default_top_k`.
3. If `top_k <= 0`: skip retrieval and send request as-is.
4. **Query rewriting** (`_rewrite_queries`):
   * Uses `QUERY_REWRITE_PROMPT` via PydanticAI.
   * Returns up to 1 original + 2 rewrites (max 3 queries total).
5. **Retrieval** (`_retrieve_memory`):
   * Candidate scopes: `[conversation_id]` plus `"global"` if `conversation_id != "global"`.
   * For each `(query, scope)` pair:
     * Calls `query_memories(...)` with `n_results = top_k * 3`.
     * Collects unique candidates across all rewrites and scopes.
   * For each candidate:
     * **Reranker score**: cross-encoder on `(primary_query, content)` where `primary_query` is the first query.
     * **Distance bonus**:
       `dist_bonus = 0 if dist is None else 1/(1 + dist)` (≈ 0–1).
     * **Recency boost**:
       * `age_days = (now_utc - created_at).days`
       * `recency = 1 / (1 + age_days / 7)`
     * **Final score**:
       `total = reranker_score + 0.1 * dist_bonus + 0.2 * recency`
   * **MMR selection** (`_mmr_select`):
     * Uses **embedding cosine similarity** (`embedding` from Chroma) as redundancy.
     * For each follow-on pick:
       * `mmr = λ * total - (1 - λ) * redundancy` with `λ = mmr_lambda` (default 0.7).
     * First item is the highest-scoring candidate (no diversity penalty).
     * Continues until `top_k` or candidates exhausted.
   * Wraps the final set into `MemoryRetrieval(entries=[MemoryEntry(...)] )`.
   * Optionally fetches short/long summaries via `get_summary_entry` and formats them as plain text strings.
6. **Optional consolidation** (`_consolidate_retrieval_entries`):
   * If more than one memory entry:
     * Calls a small LLM pass with `CONTRADICTION_PROMPT` to mark each retrieved entry as `KEEP` or `DELETE`/`UPDATE`.
     * Only entries labeled `KEEP` or `UPDATE` are kept (UPDATE doesn’t change the text, just keeps it).
7. **Prompt augmentation** (`_format_augmented_content`):
   * Builds a single user-content string:
     * Conversation summaries (short + long, if present).
     * “Long-term memory (most relevant first)” block with `[role] content`.
     * “Current message: <original latest user message>”.
   * Replaces the last user message in `request.messages` with this augmented content.
   * Returns the augmented `ChatRequest` + `MemoryRetrieval` + `conversation_id`.

**Step 2: Send to LLM**
* **Streaming (`request.stream=True`)**
  * Persist **user turn only** immediately (`_persist_turns`).
  * Forward augmented request via SSE (`_stream_and_persist_response` → `stream_chat_sse`).
  * As chunks arrive:
    * `accumulate_assistant_text` accumulates the assistant text in a buffer.
  * When stream ends:
    * Full assistant text is persisted as an **assistant turn**.
    * Post-processing runs in the background (`run_in_background`).
* **Non-streaming**
  * Call `forward_chat_request` with augmented request (excluding `memory_id`/`memory_top_k` fields).
  * Extract assistant message (`_assistant_reply_content`).
  * Persist both user and assistant turns (`_persist_turns`).
  * Attach `memory_hits` to the LLM response:
    ```json
    "memory_hits": [ { "role": ..., "content": ..., "created_at": ..., "score": ... }, ... ]
    ```
  * Run post-processing in the background (or synchronously if configured).

**Step 3: Post-processing per turn**
`_postprocess_after_turn` orchestrates:
1. **Fact extraction + summaries** (`extract_and_store_facts_and_summaries`)
   * Extract **facts** from the latest user message via `_extract_salient_facts` (assistant text is ignored).
   * **Reconcile facts** (`_reconcile_facts`):
     * Neighborhood retrieval of existing facts (`_gather_relevant_existing_memories`) using Chroma.
     * LLM call with `UPDATE_MEMORY_PROMPT` produces a list of `MemoryUpdateDecision`:
       * `ADD`, `UPDATE`, `DELETE`, `NONE` on short IDs referring to neighborhood entries.
     * Converts short IDs back to real IDs; yields:
       * `to_add` (new/updated fact texts).
       * `to_delete` (existing fact IDs to remove).
     * Safeguard: if reconciliation yields **no additions** but we had new facts, it falls back to adding the original new facts to avoid losing information.
   * Apply deletes:
     * `delete_entries` removes from Chroma.
     * `_delete_memory_files` removes corresponding Markdown files and snapshot entries.
   * Persist new facts:
     * `_prepare_fact_entries` → list of `PersistEntry(role="memory", content=...)`.
     * `_persist_entries`:
       * Writes Markdown fact files.
       * Upserts into Chroma.
   * Update per-conversation summaries:
     * Fetch prior `summary_short` and `summary_long`.
     * `_update_summaries` calls `_update_summary` twice (different `max_tokens`) with `SUMMARY_PROMPT`.
     * Summaries use the extracted facts (pre-reconciliation) as input.
     * `_persist_summary` writes `summaries/short.md` and `summaries/long.md` and upserts/updates them in Chroma (stable IDs based on `conversation_id`).
2. **Eviction / capacity control** (`_evict_if_needed`)
   * `list_conversation_entries(..., include_summary=False)` to get all non-summary entries.
   * If count exceeds `max_entries`:
     * Sort by `created_at` ascending.
     * Drop the **oldest** overflow entries (keep the newest `max_entries`).
     * Delete from Chroma and remove corresponding Markdown files via `_delete_memory_files`.

### 3. Other Flows

**Search only (`MemoryClient.search`)**
* Wraps a text query in a dummy `ChatRequest` (single user message).
* Calls `augment_chat_request` (same rewrite + retrieval pipeline).
* Returns `MemoryRetrieval` (entries only, no LLM call, no persistence).

**Add only (`MemoryClient.add`)**
* Calls `extract_and_store_facts_and_summaries` directly:
  * Treats provided `text` as a user message.
  * Runs fact extraction, reconciliation, fact persistence, and summary updates.
  * Does **not** call the chat LLM.

**External ingest (e.g., blog)**
* Not in this code snippet, but supported by:
  * Writing Markdown fact files with `role="memory"` and appropriate `conversation_id` (e.g., `"blog"`).
  * Letting `initial_index` or the file watcher upsert them into Chroma.
  * Retrieval treats these like any other conversation-scoped memories.

## Retrieval Pipeline
- Query rewriting (optional) via `QUERY_REWRITE_PROMPT`; returns up to three queries (original + rewrites) used to expand recall across conversation/global scopes.
- For each rewrite/scope: Chroma dense retrieval (`n_results = top_k * 3`) returns docs, metadatas, distances, embeddings.
- Reranking: cross-encoder scores each candidate with the primary query only (first rewrite).
- Scoring blend (per candidate):
  - `dist_bonus = 0 if dist is None else 1/(1+dist)` (bounded ~0–1).
  - `recency = 1/(1 + age_days/7)` (bounded ~0–1, recent ~1).
  - `total = reranker_score + 0.1 * dist_bonus + 0.2 * recency`.
- Diversity (MMR): embedding cosine redundancy, `mmr = λ * total - (1-λ) * redundancy`, λ default 0.7. Redundancy capped ~1, so max penalty ~0.3; applies only to follow-on picks.
- Selection: top scorer -> iterative MMR until `top_k` or pool exhausted; summaries optionally appended.

## Prompts (current)
- **Fact extraction:** `FACT_SYSTEM_PROMPT` + `FACT_INSTRUCTIONS` via PydanticAI, output list[str] (LLM call).
- **Summaries:** short/long summary prompts (`SUMMARY_PROMPT`), conditioned on prior summaries + new facts.
- **Reconcile facts:** `UPDATE_MEMORY_PROMPT` to decide ADD/UPDATE/DELETE on a neighborhood.
- **Consolidation:** `CONTRADICTION_PROMPT` used for post-retrieval cleanup (a `CONSOLIDATION_PROMPT` exists but is not wired).
- **Query rewrite:** `QUERY_REWRITE_PROMPT`.

## Known Behaviors & Observations (from a sample ingestion)
- Embeddings: default `text-embedding-3-small` (1,536-d); the blog ingest run used `embeddinggemma:300m` (768-d), which is what earlier observations refer to.
- Reranker dominates: scores ~4–6; distance/recency add ~2–4% of the total.
- MMR penalties apply when overlap exists: redundancy ~0.7–0.9 ⇒ ~0.2–0.27 drop for later picks (λ=0.7). First pick always redundancy 0.
- Some queries yield negative reranker scores; boosts don’t rescue them.
- No score normalization; weights assume reranker outputs are modestly scaled.
- Fact extraction uses the latest user turn only; summaries use those raw extracted facts (pre-reconciliation).
- Eviction based on recency + cap; duplicates rely on LLM reconcile + MMR to suppress at prompt time.

## Issues / Open Questions
- **Scale sensitivity:** Without normalizing reranker scores per query, distance/recency/MMR have minimal influence if reranker scales change (different models could swamp boosts/penalties).
- **Diversity strength:** MMR penalty max ~0.3 vs reranker deltas of several points; diversity is a light nudge.
- **Duplicate control:** LLM reconcile may miss overlaps; no deterministic `fact_key` or write-time similarity gate.
- **Model/endpoint coupling:** Requires embedding + chat models exposed on the same OpenAI-compatible base URL; failures if model IDs differ.
- **Chunking:** Simple sentence-ish splitter (800/200); no adaptive chunking or multi-granularity.
- **Recency boost:** Simple decay; no time-aware normalization or capped decay horizons.
- **Negative reranker scores:** No handling/normalization; can lead to odd ordering when combined with small boosts.
- **MMR space:** Uses embedding cosine; not using reranker-space diversity.
- **Evaluation:** No offline eval to tune λ, pool sizes, or weights; no A/B on diversity vs. pure reranker.

## Research Questions / Next Steps (for literature review)
- How do SOTA RAG/memory systems combine cross-encoder scores with secondary signals (recency, distance, diversity)? Do they normalize reranker scores per query?
- Best practices for diversity: embedding MMR vs. reranker-space MMR vs. clustering; recommended λ ranges and normalization.
- Effective duplicate suppression: deterministic keys (`fact_key`), write-time similarity thresholds, hybrid LLM + embedding gates.
- Time-aware scoring: recency decay forms, learned recency weights, or time-bucketed sampling.
- Score scaling: common normalization schemes for reranker outputs when mixing heuristics; impact on robustness across models.
- Chunking strategies: adaptive chunking, multi-scale retrieval, and their effect on diversity/overlap.
- Evaluation protocols: offline metrics and small-scale A/Bs to tune λ, pool size, and weight blending.

## Summary of Current Defaults
- `λ (MMR) = 0.7`; pool per rewrite/scope = `top_k * 3`.
- Score: `total = rr + 0.1 * dist_bonus + 0.2 * recency`.
- Embeddings: `text-embedding-3-small` (1,536-d) by default; other runs can override (e.g., `embeddinggemma:300m` in the blog ingest).
- Reranker: ONNX cross-encoder (`Xenova/ms-marco-MiniLM-L-6-v2`).
- Salience: removed.
- Diversity: embedding cosine; penalty only on follow-on selections.
- Consolidation: `CONTRADICTION_PROMPT` is used; `CONSOLIDATION_PROMPT` is defined but not currently wired.
- Fact extraction: uses latest user turn only; summaries are fed the extracted facts (pre-reconciliation).

## Research Notes & Recommendations (lit scan)

- **Score blending / normalization:** SOTA stacks normalize scores per query (min–max or z-score) before mixing reranker with metadata. Keep diversity separate. For this system: normalize reranker each request; keep `dist_bonus`/`recency` in [0,1]; blend with explicit weights (e.g., `total = rr_norm + w_dist*dist + w_recency*recency` starting around 0.2/0.3). References: OpenAI rerank cookbook; Airweave temporal relevance explainer.
- **Diversity (MMR vs alternatives):** Embedding-space MMR with λ in 0.5–0.9 is the common default; reranker-space MMR is rare; clustering is the next step up. For this system: keep embedding MMR, grid-search λ in 0.5–0.85; optionally cluster embeddings into a few groups before MMR to widen coverage. References: Carbonell & Goldstein MMR; Elastic/OpenSearch MMR blogs; VRSD (2024) on similarity/diversity.
- **Duplicate suppression:** Typical approaches combine deterministic fact keys plus a write-time similarity gate, with LLM only as a tie-breaker. For this system: add optional `fact_key` to metadata and overwrite on key collision; add a cosine threshold (e.g., <0.6 skip reconcile, >0.85 treat as update) to reduce LLM calls; keep `_reconcile_facts` for unkeyed/ambiguous cases. References: common LTR/dedupe patterns in RAG/search blogs.
- **Recency / time-aware scoring:** Standard practice uses explicit decay (often exponential half-life) and sometimes query-aware weighting for “freshness” intents. For this system: switch to `recency = exp(-ln(2) * age_days / half_life_days)` with half-life ~60–90 days for conversations (longer for global/docs); bump `w_recency` when queries mention freshness cues (“today”, dates), otherwise keep it mild. References: Elastic/App Search recency boosts; Searchcraft time-decay guide.
- **Score scaling robustness:** Per-query normalization plus simple linear blending is common; some systems softmax cross-encoder scores or learn a small linear model over features. For this system: normalize reranker + metadata features; target reranker as 60–80% of total, recency 10–30%, distance/other 0–20%; consider a tiny learned model later if you collect labels.
- **Chunking strategies:** SOTA favors structure-aware and multi-scale chunking over fixed windows. For this system: add a Markdown-aware chunker (headings, bullets, code fences) to produce semantic sections clipped by tokens; optionally index two granularities (section-level and fine chunks) with `granularity`/`parent_id` metadata and retrieve/refine within top sections. References: recent RAG chunking guides (e.g., Databricks blog) and reconstruction-focused evaluations.
- **Evaluation plan:** Best practice is offline retrieval metrics + offline generation eval + small online tests. For this system: build a 100–300 query set with known “gold” memories; grid-search λ, pool multiplier, `w_recency`, half-life on `Recall@k`/`nDCG@k`; then do manual side-by-sides of injected memories and answers; optionally A/B two configs with human “was this helpful?” feedback. References: EvidentlyAI RAG evaluation guide and standard IR metrics.
