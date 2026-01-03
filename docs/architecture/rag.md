---
icon: lucide/database
---

# Agent CLI: RAG Proxy Technical Specification

This document describes the architectural decisions, design rationale, and technical approach for the `agent-cli` RAG (Retrieval-Augmented Generation) proxy subsystem.

## High-Level Overview

*For sharing with friends who want the gist without the technical deep-dive.*

### The Problem

LLMs only know what they were trained on. They don't know your company docs, your notes, your codebase. The traditional solution is to paste relevant text into your prompt, but that's tedious and doesn't scale.

### How It Works

1. You drop files into a folder (PDFs, markdown, code, Word docs, whatever)
2. The system automatically chops them into pieces and creates searchable embeddings
3. When you ask a question, it finds the most relevant pieces and injects them into your prompt
4. The LLM answers using your documents as context

### What Makes It Different

- **Two-stage retrieval**: Most systems use a single "find similar text" step. This one does a fast first pass, then uses a smarter model to rerank results. Like doing a Google search, then having an expert review the top results before showing you.
- **File-based, not database-hidden**: Your documents stay as files. Change a file, it updates immediately. No mysterious database state. You can version control it with git.
- **Just works locally**: No cloud dependency for the indexing part.

### In One Sentence

A local proxy that gives LLMs access to your documents using smarter multi-stage retrieval instead of the naive "find similar text" approach most tools use, while keeping everything as readable files on disk.

### Related

- [rag-proxy command](../commands/rag-proxy.md) - How to run the server
- [Configuration](../configuration.md) - Config file keys and defaults
- [Memory System Architecture](memory.md) - How memory differs from RAG
- [memory command](../commands/memory.md) - Memory proxy usage

### Try It Now

Chat with your documents using [Ollama](https://ollama.com). Two options:

**Option A: With [Open WebUI](https://github.com/open-webui/open-webui) (web interface)**

```bash
# 1. Pull the required models (one-time setup)
ollama pull embeddinggemma:300m  # for document embeddings
ollama pull qwen3:4b             # for chat

# 2. Start Open WebUI (runs in background)
#    On Linux, add: --add-host=host.docker.internal:host-gateway
docker run -d -p 3000:8080 \
  -v open-webui:/app/backend/data \
  -e WEBUI_AUTH=false \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1 \
  -e OPENAI_API_KEY=dummy \
  ghcr.io/open-webui/open-webui:main

# 3. Start the RAG proxy (runs in foreground so you can watch the logs)
uvx -p 3.13 --from "agent-cli[rag]" agent-cli rag-proxy \
  --docs-folder ./my-docs \
  --openai-base-url http://localhost:11434/v1 \
  --embedding-model embeddinggemma:300m

# 4. Open http://localhost:3000, select "qwen3:4b" as model, and chat with your docs
```

**Option B: With the [openai CLI](https://github.com/openai/openai-python) (terminal, no config needed)**

```bash
# Terminal 1: Pull models and start proxy
ollama pull embeddinggemma:300m && ollama pull qwen3:4b
uvx -p 3.13 --from "agent-cli[rag]" agent-cli rag-proxy \
  --docs-folder ./my-docs \
  --openai-base-url http://localhost:11434/v1 \
  --embedding-model embeddinggemma:300m
```

```bash
# Terminal 2: Chat with your docs (env vars point to proxy)
OPENAI_BASE_URL=http://localhost:8000/v1 OPENAI_API_KEY=dummy \
  uvx openai api chat.completions.create \
  -m qwen3:4b \
  -g user "What does my documentation say about X?"
```

---

## 1. System Overview

The RAG proxy is an **OpenAI-compatible middleware** that intercepts chat requests, retrieves relevant document context, and injects it into the conversation before forwarding to an upstream LLM provider.

```
┌─────────────┐     ┌─────────────────────────────────────┐     ┌──────────────┐
│   Client    │────▶│           RAG Proxy                 │────▶│   Upstream   │
│ (any OpenAI │     │  ┌─────────┐  ┌──────────────────┐  │     │     LLM      │
│  compatible)│     │  │ Retrieve│─▶│ Augment & Forward│  │     │ (Ollama/OAI) │
└─────────────┘     │  └─────────┘  └──────────────────┘  │     └──────────────┘
                    │       ▲                             │
                    │  ┌────┴────┐                        │
                    │  │ ChromaDB│◀── File Watcher        │
                    │  │ (Vector)│    (OS-level events)   │
                    │  └─────────┘                        │
                    └─────────────────────────────────────┘
```

**Design Goals:**

- **Drop-in replacement:** Any OpenAI-compatible client works without modification.
- **File-based source of truth:** Documents live as files on disk, not in a database.
- **Real-time sync:** Changes to documents are reflected immediately.
- **Local-first:** Runs entirely on-device with no cloud dependencies.

---

## 2. Architectural Decisions

### 2.1 Two-Stage Retrieval (Bi-Encoder + Cross-Encoder)

**Decision:** Use a two-stage retrieval pipeline combining fast bi-encoder retrieval with accurate cross-encoder reranking.

**Rationale:**

- **Bi-encoders** (embedding models) are fast but less accurate—they encode query and documents independently, missing fine-grained interactions.
- **Cross-encoders** are accurate but slow—they process query-document pairs jointly but can't scale to thousands of documents.
- **Hybrid approach:** Use bi-encoder for fast initial retrieval (3x candidates), then cross-encoder to rerank the top candidates.

**Implementation:**

- **Stage 1 (Bi-encoder):** ChromaDB with configurable embedding model (default: `text-embedding-3-small`). Retrieves `top_k × 3` candidates using cosine similarity.
- **Stage 2 (Cross-encoder):** `Xenova/ms-marco-MiniLM-L-6-v2` via ONNX Runtime. Reranks candidates and returns final `top_k`.

**Trade-off:** The cross-encoder adds ~50-100ms latency but significantly improves relevance, especially for nuanced queries.

### 2.2 File-Based Document Management

**Decision:** Documents are plain files in a watched folder, not records in a database.

**Rationale:**

- **Simplicity:** Users manage documents with familiar tools (file explorer, git, rsync).
- **Transparency:** No hidden database state—what's on disk is what's indexed.
- **Portability:** Copy the folder to move your knowledge base.
- **Version control friendly:** Documents can be tracked in git.

**Implementation:**

- Watch folder specified by `--docs-folder` (default: `./rag_docs`).
- Supports nested directories.
- Automatically ignores:
  - Hidden files and directories (starting with `.`)
  - Common development directories (`__pycache__`, `node_modules`, `venv`, `build`, `dist`, etc.)
  - Package metadata (`.egg-info` directories)
  - OS metadata files (`.DS_Store`, `Thumbs.db`)

### 2.3 OS-Level File Watching

**Decision:** Use OS-level file system events for real-time index synchronization.

**Rationale:**

- **Immediate updates:** No polling delay—changes are detected instantly.
- **Efficient:** No CPU overhead from periodic scanning.
- **Cross-platform:** Works on macOS (FSEvents), Linux (inotify), and Windows (ReadDirectoryChangesW).

**Implementation:**

- Uses `watchfiles` library (Rust-based, high performance).
- Events: Create, Modify, Delete → corresponding index operations.
- Graceful handling of transient errors (file locks, permissions).

### 2.4 Hash-Based Change Detection

**Decision:** Track file content hashes to skip re-indexing unchanged files.

**Rationale:**

- **Efficiency:** Avoid expensive embedding generation for unchanged content.
- **Idempotency:** Re-running indexing produces the same result.
- **Startup optimization:** Only process files that changed since last run.

**Implementation:**

- MD5 hash of file content stored in ChromaDB metadata.
- Hash cache rebuilt from database on startup.
- File modification triggers hash comparison before re-indexing.

### 2.5 Sentence-Based Chunking with Overlap

**Decision:** Split documents on sentence boundaries with configurable overlap.

**Rationale:**

- **Semantic coherence:** Sentences are natural units of meaning; splitting mid-sentence loses context.
- **Overlap for continuity:** Ensures concepts spanning chunk boundaries aren't lost.
- **Configurable:** Different document types may need different chunk sizes.

**Implementation:**

- Default: 1200 characters per chunk, 200 character overlap.
- Prefers separators in order: blank lines, newlines, ". ", ", ", and spaces.
- Fallback to character-based splitting when no separator fits.

### 2.6 Tool-Augmented Retrieval

**Decision:** Provide an optional `read_full_document` tool for when snippets are insufficient.

**Rationale:**

- **Chunk limitations:** Sometimes the answer requires seeing the full document context.
- **Agent flexibility:** Let the LLM decide when it needs more information.
- **Efficiency:** Only fetch full documents when necessary, not always.

**Implementation:**

- Tool available when `--rag-tools` flag is enabled (default: true).
- Path traversal protection prevents access outside the docs folder.
- Supports all indexed file types.

### 2.7 Rich Document Support

**Decision:** Support PDF, Word, PowerPoint, Excel, and HTML in addition to plain text.

**Rationale:**

- **Real-world documents:** Knowledge bases often contain more than just markdown.
- **Unified interface:** Users don't need separate tools for different formats.

**Implementation:**

- **Text files (direct read):** `.txt`, `.md`, `.py`, `.json`, `.yaml`, `.yml`, `.toml`, `.rs`, `.go`, `.c`, `.cpp`, `.h`, `.js`, `.ts`, `.sh`, `.rst`, `.ini`, `.cfg`
- **Rich documents (via MarkItDown):** `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`, `.htm`, `.csv`, `.xml`

---

## 3. Data Model

### 3.1 Document Chunks in ChromaDB

Each document is split into chunks and stored with metadata:

| Field          | Description                                |
| -------------- | ------------------------------------------ |
| `id`           | `{relative_path}:chunk:{index}`            |
| `document`     | The chunk text content                     |
| `embedding`    | Vector from configured embedding model     |
| `source`       | File name (e.g., `guide.md`)               |
| `file_path`    | Relative path from docs folder             |
| `file_type`    | File extension                             |
| `chunk_id`     | Index within the file (0, 1, 2, ...)       |
| `total_chunks` | Total chunks in the file                   |
| `indexed_at`   | ISO 8601 timestamp                         |
| `file_hash`    | MD5 of file content (for change detection) |

### 3.2 Request Extensions

The proxy accepts standard OpenAI chat completion requests with optional RAG-specific fields:

| Field              | Default        | Description                              |
| ------------------ | -------------- | ---------------------------------------- |
| `rag_top_k`        | Server default | Number of chunks to retrieve             |
| `rag_enable_tools` | `true`         | Enable/disable `read_full_document` tool |

### 3.3 Response Extensions

Responses include source attribution:

```json
{
  "choices": [...],
  "rag_sources": [
    {"source": "guide.md", "path": "docs/guide.md", "chunk_id": 2, "score": 0.85}
  ]
}
```

---

## 4. Request Processing Pipeline

### 4.1 Retrieval Flow

1. **Extract query:** Find the last user message in the conversation.
2. **Dense retrieval:** Query ChromaDB for `top_k × 3` similar chunks.
3. **Cross-encoder reranking:** Score each candidate against the query, sort by relevance.
4. **Select top-k:** Return the highest-scoring chunks.
5. **Format context:** Build a structured context string with source citations.

### 4.2 Context Injection

The retrieved context is injected into a system prompt that instructs the LLM to:

- **Context Truncation:** The context is strictly capped at 12,000 characters (approx. 3,000 tokens) to ensure it fits within standard context windows.
- Use context only if relevant to the question.
- Cite sources using `[Source: filename]` format.
- Fall back to general knowledge if context is irrelevant.
- Use the `read_full_document` tool if snippets are insufficient (when enabled).

### 4.3 Upstream Forwarding

After augmentation, the request is forwarded to the configured upstream LLM provider. The proxy supports:

- **Streaming responses:** SSE passthrough with source metadata in final chunk.
- **Non-streaming responses:** JSON response with `rag_sources` field.

---

## 5. Indexing Pipeline

### 5.1 Startup Sequence

1. Initialize ChromaDB collection with embedding function.
2. Load cross-encoder model (ONNX).
3. Rebuild file hash cache from existing metadata.
4. Start file watcher for real-time updates.
5. Run initial index scan in background thread.

### 5.2 Initial Index

On startup, the system synchronizes the index with disk state:

- **Parallel processing:** 4 worker threads for embedding generation.
- **Batching:** Upserts to ChromaDB are batched (10 chunks at a time) to maintain stability and avoid timeouts.
- **Change detection:** Skip files with unchanged hashes.
- **Stale cleanup:** Remove chunks for files no longer on disk.

### 5.3 Incremental Updates

File system events trigger incremental updates:

- **File created/modified:** Recompute hash, re-chunk, re-embed if changed.
- **File deleted:** Remove all chunks from index.

---

## 6. Configuration Reference

| Parameter                        | Default                  | Description                          |
| -------------------------------- | ------------------------ | ------------------------------------ |
| `--docs-folder`                  | `./rag_docs`             | Directory to watch for documents     |
| `--chroma-path`                  | `./rag_db`               | ChromaDB persistence directory       |
| `--openai-base-url`              | _required_               | Upstream LLM provider URL            |
| `--embedding-model`              | `text-embedding-3-small` | Model for vector embeddings          |
| `--limit`                        | `3`                      | Default number of chunks to retrieve |
| `--rag-tools` / `--no-rag-tools` | enabled                  | Enable `read_full_document` tool     |
| `--host`                         | `0.0.0.0`                | Server bind address                  |
| `--port`                         | `8000`                   | Server bind port                     |

---

## 7. API Endpoints

| Endpoint               | Method | Description                                  |
| ---------------------- | ------ | -------------------------------------------- |
| `/v1/chat/completions` | POST   | OpenAI-compatible chat with RAG augmentation |
| `/reindex`             | POST   | Trigger manual reindexing of all files       |
| `/files`               | GET    | List all indexed files with chunk counts     |
| `/health`              | GET    | Health check with configuration info         |
| `/*`                   | \*     | Proxy passthrough to upstream provider       |

---

## 8. Comparison with Memory System

See [Memory System Architecture](memory.md) for the memory-specific pipeline and storage details.

The RAG proxy and memory system share some infrastructure but serve different purposes:

| Aspect          | RAG Proxy                  | Memory System                       |
| --------------- | -------------------------- | ----------------------------------- |
| **Purpose**     | Query static documents     | Remember conversation facts         |
| **Data source** | Files on disk              | Extracted from conversations        |
| **Retrieval**   | Bi-encoder + cross-encoder | + Recency weighting + MMR diversity |
| **Write path**  | File watcher (external)    | Fact extraction (LLM-driven)        |
| **Scoring**     | Pure relevance             | Relevance + recency + diversity     |
| **Persistence** | ChromaDB only              | Markdown files + ChromaDB + Git     |

**Why no recency/MMR in RAG?**

- Documents don't have temporal relevance like memories.
- Document chunks are typically more heterogeneous than repeated facts.

---

## 9. Security Considerations

- **Path traversal protection:** The `read_full_document` tool validates that requested paths are within the docs folder.
- **API key passthrough:** Bearer tokens from clients are forwarded to upstream; server keys used as fallback.
- **CORS:** Permissive by default (`*`) for local development; should be restricted in production.
