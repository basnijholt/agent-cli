# Memory System Overview (Current Implementation)

This document captures what the agent_cli memory system does today. It summarizes the architecture, retrieval/ranking math, prompts, and design choices.

## One-paragraph overview
We run a self-hostable memory service that ingests chat turns, extracts facts, and stores everything in a Chroma vector DB. At query time we take the latest user message, retrieve dense candidates from Chroma, rerank them with a cross-encoder, filter by relevance threshold, and blend with recency decay. Finally, we apply MMR on embedding cosine to keep the final top-k diverse. We then inject those memories (plus a conversation summary) into the chat request and forward it to an OpenAI-compatible LLM. Summaries and fact reconciliation are LLM-driven; retrieval is fast and deterministic.

## Architecture & Data Flow (Current Implementation)

### 1. Main Components

**Runtime service**

* **FastAPI app (`agent_cli.memory.api`)**
  * `POST /v1/chat/completions`
    * Accepts an OpenAI-style chat request plus `memory_id` / `memory_top_k` / `memory_recency_weight` / `memory_score_threshold`.
    * Extracts bearer token from `Authorization` and passes it through as the chat API key.
    * Delegates to `MemoryClient.chat(...)`.
  * `GET /health` returns basic config.
  * Startup/shutdown events start/stop a background file watcher.

* **MemoryClient (`agent_cli.memory.client.MemoryClient`)**
  * Owns:
    * `memory_path`: root dir for Markdown + Chroma.
    * `collection`: Chroma collection initialized via `init_memory_collection`.
    * `index`: in-memory index of Markdown files (`MemoryIndex`).
    * `reranker_model`: ONNX cross-encoder (via `get_reranker_model()`).
    * Config: `embedding_model` (default `text-embedding-3-small`), `default_top_k`, `max_entries`, `mmr_lambda`, `recency_weight`, `score_threshold`, `enable_summarization`.
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
    * `summaries/summary.md` (role `summary`)
  * Each file has:
    * Front matter: `id`, `conversation_id`, `role`, `created_at`, optional `summary_kind`.
    * Body: plain text content.

* **Vector store (`agent_cli.memory.store`)**
  * One Chroma collection per memory root (default name `"memory"`, stored under `<memory_path>/chroma`).
  * All conversations share this collection and are keyed by `metadata.conversation_id`.
  * Helpers:
    * `upsert_memories(...)`: wraps Chroma upsert.
    * `query_memories(...)`: dense retrieval with embeddings (`include=["embeddings"]`).
    * `get_summary_entry(...)`: fetches the (single) summary doc for a conversation.
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
  * All model calls (chat, fact extraction, summarization, reconciliation) go through an OpenAI-compatible base URL:
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
   * Optional: `memory_id`, `memory_top_k`, `memory_recency_weight`, `memory_score_threshold`.
2. `MemoryClient.chat` wraps this into a `ChatRequest` (Pydantic model) and calls:
   ```python
   process_chat_request(...)
   ```

**Step 1: Augment request with memory (`augment_chat_request`)**
1. Identify **latest user message**.
2. Determine:
   * `conversation_id = request.memory_id or "default"`.
   * `top_k = request.memory_top_k or default_top_k`.
3. If `top_k <= 0`: skip retrieval and send request as-is.
4. **Retrieval** (`_retrieve_memory`):
   * Candidate scopes: `[conversation_id]` plus `"global"` if `conversation_id != "global"`.
   * For each scope:
     * Calls `query_memories(...)` with `n_results = top_k * 3`.
     * Collects unique candidates.
   * For each candidate:
     * **Reranker score**: cross-encoder on `(query, content)`.
     * **Relevance**: `sigmoid(reranker_score)` (0–1).
     * **Filter**: If `Relevance < score_threshold` (default 0.35), discard candidate.
     * **Recency boost**:
       * `recency = exp(-age_days / 30.0)` (exponential decay).
     * **Final score**:
       * `total = (1 - w) * relevance + w * recency` (w = `recency_weight`, default 0.2).
   * **MMR selection** (`_mmr_select`):
     * Uses **embedding cosine similarity** (`embedding` from Chroma) as redundancy.
     * For each follow-on pick:
       * `mmr = λ * total - (1 - λ) * redundancy` with `λ = mmr_lambda` (default 0.7).
     * Continues until `top_k` or candidates exhausted.
   * Wraps the final set into `MemoryRetrieval(entries=[MemoryEntry(...)] )`.
   * Optionally fetches single `summary` via `get_summary_entry`.
5. **Prompt augmentation** (`_format_augmented_content`):
   * Builds a single user-content string:
     * Conversation summary (if present).
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
  * Call `forward_chat_request` with augmented request (excluding memory fields).
  * Extract assistant message (`_assistant_reply_content`).
  * Persist both user and assistant turns (`_persist_turns`).
  * Attach `memory_hits` to the LLM response:
    ```json
    "memory_hits": [ { "role": ..., "content": ..., "created_at": ..., "score": ... }, ... ]
    ```
  * Run post-processing in the background.

**Step 3: Post-processing per turn**
`_postprocess_after_turn` orchestrates:
1. **Fact extraction + summaries** (`extract_and_store_facts_and_summaries`)
   * Extract **facts** from the latest user message via `_extract_salient_facts` (assistant text is ignored).
   * **Reconcile facts** (`_reconcile_facts`):
     * Neighborhood retrieval of existing facts (`_gather_relevant_existing_memories`) using Chroma.
     * LLM call with `UPDATE_MEMORY_PROMPT` produces a list of `MemoryUpdateDecision`:
       * `ADD`, `UPDATE`, `DELETE`, `NONE`.
     * Converts short IDs back to real IDs; yields `to_add`, `to_delete`.
     * Safeguard: if reconciliation yields **no additions** but we had new facts, fallback to adding original new facts.
   * Apply deletes:
     * `delete_entries` removes from Chroma.
     * `_delete_memory_files` removes corresponding Markdown files and snapshot entries.
   * Persist new facts:
     * `_prepare_fact_entries` → `_persist_entries` (Markdown + Chroma).
   * Update per-conversation summary:
     * Fetch prior `summary`.
     * `_update_summary` calls LLM with `SUMMARY_PROMPT`.
     * `_persist_summary` writes `summaries/summary.md` and upserts to Chroma.
2. **Eviction / capacity control** (`_evict_if_needed`)
   * `list_conversation_entries` to get all non-summary entries.
   * If count exceeds `max_entries`:
     * Drop the **oldest** overflow entries.
     * Delete from Chroma and filesystem.

### 3. Other Flows

**Search only (`MemoryClient.search`)**
* Wraps a text query in a dummy `ChatRequest` (single user message).
* Calls `augment_chat_request` (same retrieval pipeline).
* Returns `MemoryRetrieval` (entries only, no LLM call, no persistence).

**Add only (`MemoryClient.add`)**
* Calls `extract_and_store_facts_and_summaries` directly:
  * Treats provided `text` as a user message.
  * Runs fact extraction, reconciliation, fact persistence, and summary updates.
  * Does **not** call the chat LLM.

## Retrieval Pipeline (Lite Architecture)
- **Search**: Chroma dense retrieval (`n_results = top_k * 3`) returns docs, metadatas, distances, embeddings.
- **Reranking**: cross-encoder scores each candidate with the query.
- **Filtering**: `relevance = sigmoid(reranker_score)`. Discard if `relevance < score_threshold` (default 0.35).
- **Scoring Blend**:
  - `recency = exp(-age_days / 30.0)` (exponential decay).
  - `total = (1 - w) * relevance + w * recency`. (default `w=0.2`).
- **Diversity (MMR)**: embedding cosine redundancy, `mmr = λ * total - (1-λ) * redundancy`, λ default 0.7.
- **Selection**: top scorer -> iterative MMR until `top_k` or pool exhausted; summary optionally appended.

## Prompts (current)
- **Fact extraction:** `FACT_SYSTEM_PROMPT` + `FACT_INSTRUCTIONS`.
- **Summary:** `SUMMARY_PROMPT`.
- **Reconcile facts:** `UPDATE_MEMORY_PROMPT`.

## Summary of Current Defaults
- `λ (MMR) = 0.7`; pool per scope = `top_k * 3`.
- `recency_weight = 0.2`; `score_threshold = 0.35`.
- Score: `total = 0.8 * sigmoid(rr) + 0.2 * exp(-age/30)`.
- Embeddings: `text-embedding-3-small` (1,536-d) by default.
- Reranker: ONNX cross-encoder (`Xenova/ms-marco-MiniLM-L-6-v2`).
