# Agent CLI: Memory System Technical Specification

This document serves as the authoritative technical reference for the `agent-cli` memory subsystem. It details the component architecture, data structures, internal algorithms, and control flows implemented in the codebase.

## 1. Architectural Components

The memory system is composed of layered Python modules, separating the API surface from the core logic and storage engines.

### 1.1 Runtime Layer
*   **`agent_cli.memory.api` (FastAPI):**
    *   Exposes `POST /v1/chat/completions` as an OpenAI-compatible endpoint.
    *   Handles request validation (`ChatRequest` pydantic model).
    *   Manages lifecycle: starts/stops the `MemoryClient` file watcher on app startup/shutdown.
*   **`agent_cli.memory.client.MemoryClient`:**
    *   The primary entry point. Orchestrates the interaction between the Logic Engine, File Store, and Vector Index.
    *   **State:** Holds references to the `chromadb.Collection`, `MemoryIndex` (in-memory file map), and `reranker_model` (ONNX session).
    *   **Methods:** `chat()` (end-to-end), `search()` (retrieval only), `add()` (injection only).

### 1.2 Logic Engine (`agent_cli.memory.engine`)
*   **`agent_cli.memory.engine`:** The high-level orchestrator.
    *   **`process_chat_request`:** Main entry point. Handles synchronous vs. asynchronous (streaming) execution paths and coordinates the pipeline.
*   **`agent_cli.memory._retrieval`:** The "Read" path logic.
    *   **`augment_chat_request`:** Executes retrieval, reranking, recency weighting, MMR selection, and prompt injection.
*   **`agent_cli.memory._ingest`:** The "Write" path logic.
    *   **`extract_and_store_facts_and_summaries`:** Runs fact extraction, reconciliation, summarization, and triggers persistence.

### 1.3 Storage Layer
*   **`agent_cli.memory._persistence`:**
    *   Handles the coordination of writing to disk and updating the vector DB (`persist_entries`, `evict_if_needed`).
*   **`agent_cli.memory._files` (File Store):**
    *   Source of Truth. Manages reading/writing Markdown files with YAML front matter.
    *   Handles path resolution: `<memory_path>/entries/<conversation_id>/{facts,turns,summaries}/`.
*   **`agent_cli.memory._store` (Vector Store):**
    *   Wraps `chromadb`.
    *   Handles embedding generation (via `text-embedding-3-small` or local models).
    *   Implements `query_memories` with dense retrieval parameters (`n_results`, filtering).
*   **`agent_cli.memory._indexer` (Index Sync):**
    *   Maintains `memory_index.json` (file hash snapshot) to keep ChromaDB in sync with the filesystem.
    *   **Watcher:** Uses `watchfiles` to detect OS-level file events (Create/Modify/Delete) and trigger incremental vector updates.
*   **`agent_cli.memory._git` (Versioning):**
    *   Provides asynchronous Git integration for the memory store.
    *   Initialize repo on startup and commits changes after memory updates.

---

## 2. Data Structures & Schema

### 2.1 File System Layout
Memories are stored as Markdown files with YAML front matter in `<memory_path>/entries/<conversation_id>/`.

**Active Directory Structure:**
```text
entries/
  <conversation_id>/
    facts/
      <timestamp>__<uuid>.md       # Extracted atomic facts
    turns/
      user/<timestamp>__<uuid>.md   # Raw user messages
      assistant/
        <timestamp>__<uuid>.md     # Raw assistant responses
    summaries/
      L1/
        chunk_0.md                 # Level 1: Individual chunk summaries
        chunk_1.md
      L2/
        group_0.md                 # Level 2: Group summaries (groups of ~5 L1s)
      L3/
        final.md                   # Level 3: Final synthesized summary
```

**Deleted Directory Structure (Soft Deletes):**
Deleted files are **moved** (not destroyed) to preserve audit trails.
```text
entries/
  <conversation_id>/
    deleted/
      facts/
        <timestamp>__<uuid>.md
      summaries/
        L1/, L2/, L3/              # Tombstoned summary levels
```

### 2.2 File Format
**Front Matter (YAML):**
*   `id`: UUIDv4 (summaries use a deterministic ID suffix).
*   `role`: `memory` (fact), `user`, `assistant`, or `summary`.
*   `conversation_id`: Scope key.
*   `created_at`: ISO 8601 timestamp (used for recency scoring).
*   `summary_kind`: Present only on summaries.
*   `replaced_by`: Present only on tombstones when an update replaces a fact.

**Body:** The semantic content (e.g., "User lives in San Francisco").

### 2.3 Vector Schema (ChromaDB)
All entries share a single collection but are partitioned by metadata.
*   **ID:** Matches file UUID.
*   **Embedding:** 1536d (OpenAI) or 384d (MiniLM).
*   **Metadata:** Mirrors front matter (`role`, `conversation_id`, `created_at`, `summary_kind`, `replaced_by`) for pre-filtering and maintenance.

### 2.4 Versioning (Git)
When `enable_git_versioning` is true, the memory system maintains a local Git repository at `memory_path`.
*   **Initialization:** Creates a repo and `.gitignore` (ignoring `chroma/`, `memory_index.json`, etc.) if missing.
*   **Commits:** Automatically stages and commits all changes (adds, modifications, soft deletes) after every turn or fact update.
*   **Execution:** Uses asynchronous subprocess calls (`asyncio.create_subprocess_exec`) to prevent blocking the main event loop during git operations.

---

## 3. The Read Path (Retrieval Pipeline)

Executed synchronously during `augment_chat_request`.

### Step 1: Scope & Retrieval
*   **Scopes:** Queries `conversation_id` bucket + `global` bucket.
*   **Density:** Calls `collection.query()` retrieving `top_k * 3` candidates per scope using Cosine Similarity.
*   **Filtering:** Excludes `role="summary"` (summaries are handled separately).

### Step 2: Cross-Encoder Reranking
*   **Model:** `Xenova/ms-marco-MiniLM-L-6-v2` (ONNX, quantized).
*   **Input:** Pairs of `(user_query, memory_content)`.
*   **Output:** Raw logit score.
*   **Normalization:** `relevance = sigmoid(raw_score)`.
*   **Thresholding:** Candidates with `relevance < score_threshold` (default 0.35) are hard-pruned.

### Step 3: Recency Scoring
Combines semantic relevance with temporal proximity.
*   **Formula:** `recency_score = exp(-age_in_days / 30.0)`
*   **Final Score:** `(1 - w) * relevance + w * recency_score`
    *   `w` (`recency_weight`) defaults to `0.2`.

### Step 4: Diversity (MMR)
Applies Maximal Marginal Relevance to select the final `top_k` from the ranked pool.
*   **Goal:** Prevent redundant memories (e.g., 5 variations of "User likes apples").
*   **Formula:** `mmr_score = λ * relevance - (1 - λ) * max_sim(candidate, selected)`
    *   `λ` (`mmr_lambda`) defaults to `0.7`.
    *   `max_sim` uses the cosine similarity of embeddings provided by Chroma.

### Step 5: Injection
*   **Structure:**
    1.  **Summary:** Injected if available for the conversation (`role="summary"`).
    2.  **Memories:** The top-k retrieved facts/turns, formatted as `[<role>] <content>` (scores are not shown).
    3.  **Current Turn:** The user's actual message.

---

## 4. The Write Path (Ingestion Pipeline)

Executed via `_postprocess_after_turn` (background task).

### 4.1 Streaming vs. Non-Streaming
*   **Streaming:**
    *   User turn persisted immediately (stored under `turns/user`).
    *   Assistant tokens accumulated in memory buffer.
    *   Full assistant text persisted on stream completion (stored under `turns/assistant`), then background post-processing runs.
*   **Non-Streaming:**
    *   User and Assistant turns persisted sequentially after full response is received, followed by post-processing.

### 4.2 Fact Extraction
*   **Input:** Latest user message only (assistant/system text is ignored).
*   **Prompt:** `FACT_SYSTEM_PROMPT`. Extracts 0–3 atomic, standalone statements via PydanticAI.
*   **Output:** JSON list of strings. Failures fall back to `[]`.

### 4.3 Reconciliation (Memory Management)
Resolves contradictions using a "Search-Decide-Update" loop with complete enumeration.
1.  **Local Search:** For each new fact, retrieve a small neighborhood of existing `role="memory"` entries for the conversation.
2.  **LLM Decision:** Uses `UPDATE_MEMORY_PROMPT` to compare `new_facts` vs `existing_memories`. The model must return **all memories** (existing + new) with explicit events for each.
    *   **Decisions:** `ADD`, `UPDATE`, `DELETE`, `NONE`.
    *   If no existing memories are found, all new facts are added directly.
    *   On LLM/network failure, defaults to adding all new facts.
3.  **Execution:**
    *   **Adds:** Creates new fact files and upserts to Chroma.
    *   **Updates:** Implemented as delete + add with a fresh ID; tombstones record `replaced_by`.
    *   **Deletes:** Soft-deletes files (moved under `deleted/`) and removes from Chroma.

### 4.4 Summarization (Adaptive Hierarchical)
Uses the `agent_cli.summarizer` module for research-backed adaptive summarization.

*   **Level Selection:** Automatically determines summarization depth based on token count:
    *   `NONE` (< 100 tokens): No summary needed, facts only.
    *   `BRIEF` (100-500 tokens): Single-sentence summary (~20% compression).
    *   `STANDARD` (500-3000 tokens): Paragraph summary (~12% compression).
    *   `DETAILED` (3000-15000 tokens): Chunked summaries + meta-summary (~7% compression).
    *   `HIERARCHICAL` (> 15000 tokens): Full L1/L2/L3 tree structure.
*   **Input:** Previous L3 summary (if any) + newly extracted facts.
*   **Persistence:** Stores summaries in `summaries/L1/`, `L2/`, `L3/` subdirectories with YAML front matter containing compression metrics.
*   **See:** `docs/architecture/summarizer.md` for detailed algorithm specification.

### 4.5 Eviction
*   **Trigger:** If total entries in conversation > `max_entries` (default 500).
*   **Strategy:** Sorts by `created_at` (ascending) and deletes the oldest `facts` or `turns` until count is within limit. Summaries are exempt.

### 4.6 Versioning
If `enable_git_versioning` is enabled, an asynchronous git commit is triggered at the end of the post-processing pipeline to snapshot the latest state of the memory store.

---

## 5. Prompt Logic Specifications

To replicate the system behavior, the following prompt strategies are required.

### 5.1 Fact Extraction (`FACT_SYSTEM_PROMPT`)
*   **Goal:** Extract 1-3 concise, atomic facts from the user message.
*   **Constraints:** Ignore assistant text. No acknowledgements. Output JSON list of strings.
*   **Example:** "My wife is Anne" -> `["The user's wife is named Anne"]`.

### 5.2 Reconciliation (`UPDATE_MEMORY_PROMPT`)
*   **Goal:** Compare `new_facts` against `existing_memories` and return **all memories** (existing + new) with explicit events.
*   **Approach:** The model must enumerate every memory in its response, forcing deliberate decisions rather than implicit omissions.
*   **Operations:**
    *   **ADD:** New information not present in existing memories (generates a new sequential ID).
    *   **UPDATE:** Refines existing information about the **same topic** (keeps the existing ID).
    *   **DELETE:** Explicitly contradicts existing information (e.g., "I hate pizza" vs "I love pizza").
    *   **NONE:** Existing memory is unrelated to new facts, or new fact is an exact duplicate.
*   **Output constraints:** JSON list containing all memories; each existing memory must have an event; new unrelated facts must be ADDed; no prose or code fences.

### 5.3 Summarization (Adaptive Prompts)
The summarizer uses level-specific prompts from `agent_cli.summarizer._prompts`:
*   **`BRIEF_PROMPT`:** Single-sentence distillation for short content.
*   **`STANDARD_PROMPT`:** Paragraph summary with prior context integration.
*   **`CHUNK_PROMPT`:** Individual chunk summarization for hierarchical processing.
*   **`META_PROMPT`:** Synthesizes multiple chunk summaries into cohesive narrative.
*   **`ROLLING_PROMPT`:** Integrates new facts with existing summary.
*   **Content-type variants:** `CONVERSATION_PROMPT`, `JOURNAL_PROMPT`, `DOCUMENT_PROMPT` for domain-specific summarization.

---

## 6. Configuration Reference

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `memory_path` | `./memory_db` | Root directory for file storage. |
| `embedding_model` | `text-embedding-3-small` | ID for embedding generation (OpenAI or local path). |
| `default_top_k` | `5` | Target number of memories to retrieve. |
| `max_entries` | `500` | Hard cap on memories per conversation. |
| `mmr_lambda` | `0.7` | Diversity weighting (1.0 = pure relevance). |
| `recency_weight` | `0.2` | Score weight for temporal proximity. |
| `score_threshold` | `0.35` | Minimum semantic relevance to consider. |
| `enable_summarization` | `True` | Toggle for summary generation loop. |
| `openai_base_url` | *required* | Base URL for LLM calls (can point to OpenAI-compatible proxies). |
| `enable_git_versioning` | `False` | Toggle to enable/disable Git versioning of the memory store. |
| `start_watcher` | `False` | Start a file watcher to keep Chroma in sync with on-disk edits. |
