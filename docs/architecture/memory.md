---
icon: lucide/brain
---

# Agent CLI: Memory System Technical Specification

This document serves as the authoritative technical reference for the `agent-cli` memory subsystem. It details the component architecture, data structures, internal algorithms, and control flows implemented in the codebase.

## High-Level Overview

*For sharing with friends who want the gist without the technical deep-dive.*

### The Problem

LLMs are stateless. Every conversation starts fresh. They don't remember you told them your wife's name is Anne, or that you hate mushrooms, or that you're working on a Python project.

### How It Works

1. After each message, an LLM extracts atomic facts ("User's wife is named Anne")
2. These facts get stored and made searchable
3. Before your next message, relevant memories get pulled in automatically
4. The LLM now "remembers" things about you

### What Makes It Different

- **Reconciliation, not just accumulation**: If you say "I love pizza" today and "I hate pizza" next month, most systems would just store both. This one uses an LLM to detect the contradiction and update the old fact. It actively manages memory, not just appends to it.

- **Recency-aware**: Recent memories score higher than old ones. What you said yesterday matters more than what you said six months ago for most queries.

- **Diversity selection**: If you've mentioned five different times that you like coffee, it won't waste your context window by injecting all five variations. It picks the most relevant one and moves on.

- **Human-readable persistence**: Every memory is a markdown file on disk. You can read them, edit them, delete them. Optional git integration means you have full version history of everything the system remembers.

- **Summarization**: For long conversations, it maintains a rolling summary so you don't hit token limits.

### In One Sentence

A local-first system that gives LLMs persistent memory across conversations, with the twist that everything stays human-readable files on disk and it uses smarter scoring (recency + diversity + relevance) instead of just embedding similarity.

### Related

- [memory command](../commands/memory.md) - How to run the memory proxy and add memories
- [Configuration](../configuration.md) - Config file keys and defaults
- [RAG System Architecture](rag.md) - Related retrieval stack for documents
- [rag-proxy command](../commands/rag-proxy.md) - Document retrieval server

### Try It Now

Get an LLM that remembers you using [Ollama](https://ollama.com). Two options:

**Option A: With [Open WebUI](https://github.com/open-webui/open-webui) (web interface)**

```bash
# 1. Pull the required models (one-time setup)
ollama pull embeddinggemma:300m  # for memory embeddings
ollama pull qwen3:4b             # for chat

# 2. Start Open WebUI (runs in background)
#    On Linux, add: --add-host=host.docker.internal:host-gateway
docker run -d -p 3000:8080 \
  -v open-webui:/app/backend/data \
  -e WEBUI_AUTH=false \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8100/v1 \
  -e OPENAI_API_KEY=dummy \
  ghcr.io/open-webui/open-webui:main

# 3. Start the memory proxy (runs in foreground so you can watch the logs)
uvx -p 3.13 --from "agent-cli[memory]" agent-cli memory proxy \
  --memory-path ./my-memories \
  --openai-base-url http://localhost:11434/v1 \
  --embedding-model embeddinggemma:300m

# 4. Open http://localhost:3000, select "qwen3:4b" as model, and start chatting — it remembers you
```

**Option B: With the [openai CLI](https://github.com/openai/openai-python) (terminal, no config needed)**

```bash
# Terminal 1: Pull models and start proxy
ollama pull embeddinggemma:300m && ollama pull qwen3:4b
uvx -p 3.13 --from "agent-cli[memory]" agent-cli memory proxy \
  --memory-path ./my-memories \
  --openai-base-url http://localhost:11434/v1 \
  --embedding-model embeddinggemma:300m
```

```bash
# Terminal 2: Chat from the terminal (env vars point to proxy)
export OPENAI_BASE_URL=http://localhost:8100/v1 OPENAI_API_KEY=dummy

# Tell it something about yourself
uvx openai api chat.completions.create -m qwen3:4b -g user "My name is Alice and I love hiking"

# Later, ask if it remembers
uvx openai api chat.completions.create -m qwen3:4b -g user "What's my name?"
```

---

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
      summary.md                   # The single rolling summary of the conversation
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
        summary.md                 # Tombstoned summary
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
*   **Embedding:** Dimensionality depends on the configured embedding model (e.g., `text-embedding-3-small` is 1536d).
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
*   **Normalization:** Min-max scaling across the candidate batch (best match = 1.0, worst = 0.0).
*   **Thresholding:** If `score_threshold` is set, candidates below it are pruned. Default is `None` (no filtering).

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
Resolves contradictions using a "Search-Decide-Update" loop.
1.  **Local Search:** For each new fact, retrieve a small neighborhood of existing `role="memory"` entries for the conversation.
2.  **LLM Decision:** Uses `UPDATE_MEMORY_PROMPT` (examples + strict JSON schema) to compare `new_facts` vs `existing_memories`.
    *   **Decisions:** `ADD`, `UPDATE`, `DELETE`, `NONE`.
    *   If no existing memories are found, all new facts are added directly.
    *   On LLM/network failure, defaults to adding all new facts.
    *   Safeguard: if the model returns only deletes/empties, the new facts are still added to avoid data loss.
3.  **Execution:**
    *   **Adds:** Creates new fact files and upserts to Chroma.
    *   **Updates:** Implemented as delete + add with a fresh ID; tombstones record `replaced_by`.
    *   **Deletes:** Soft-deletes files (moved under `deleted/`) and removes from Chroma.

### 4.4 Summarization
*   **Input:** Previous summary (if any) + newly extracted facts.
*   **Prompt:** `SUMMARY_PROMPT` (updates the running summary).
*   **Persistence:** Writes a single `summaries/summary.md` per conversation (deterministic doc ID).

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
*   **Goal:** Compare `new_facts` against `existing_memories` (id + text) and output structured decisions.
*   **Operations:**
    *   **ADD:** New information (generates a new ID).
    *   **UPDATE:** Refines existing information (uses the provided short ID).
    *   **DELETE:** Contradicts existing information (e.g., "I hate pizza" vs "I love pizza"). **If deleting because of a replacement, the new fact must also be returned (ADD or UPDATE).**
    *   **NONE:** Fact already exists or is irrelevant.
*   **Output constraints:** JSON list only; no prose/code fences; IDs for UPDATE/DELETE/NONE must come from the provided list.

### 5.3 Summarization (`SUMMARY_PROMPT`)
*   **Goal:** Maintain a concise running summary.
*   **Constraints:** Aggregate related facts. Drop transient chit-chat. Focus on durable info.

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
| `score_threshold` | `None` | Minimum semantic relevance to consider (no filtering by default). |
| `enable_summarization` | `True` | Toggle for summary generation loop. |
| `openai_base_url` | *required* | Base URL for LLM calls (can point to OpenAI-compatible proxies). |
| `enable_git_versioning` | `True` | Toggle to enable/disable Git versioning of the memory store. |
| `start_watcher` | `False` | Start a file watcher to keep Chroma in sync with on-disk edits. |
