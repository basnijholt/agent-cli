# Agent CLI: Adaptive Summarizer Technical Specification

This document describes the architectural decisions, design rationale, and technical approach for the `agent-cli` adaptive summarization subsystem.

## 1. System Overview

The adaptive summarizer provides **content-aware compression** that scales summarization depth with input complexity. Rather than applying a one-size-fits-all approach, it automatically selects the optimal strategy based on token count.

```
Input Content ──▶ Token Count ──▶ Level Selection ──▶ Strategy
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │                               │                               │
   < 100 tokens                   500-15000 tokens                > 15000 tokens
        │                               │                               │
   No summary needed            Chunked processing              Hierarchical tree
                                  + meta-synthesis                  (L1/L2/L3)
```

**Design Goals:**

- **Adaptive compression:** Match summarization depth to content complexity.
- **Research-informed:** Draws techniques from Letta's memory management.
- **Hierarchical structure:** Preserve detail at multiple granularities for large content.
- **Content-type awareness:** Domain-specific prompts for conversations, journals, documents.

---

## 2. Research Foundations

### 2.1 Letta (MemGPT) Contributions

**Reference:** arXiv:2310.08560

Letta's approach to memory management introduced the **partial eviction** technique adopted here: rather than discarding old content entirely, compress a portion to summaries while keeping recent content detailed. This maps to our hierarchical L1/L2/L3 structure where L1 preserves chunk-level detail and L3 provides high-level synthesis.

### 2.2 Mem0 Contributions

**Reference:** arXiv:2504.19413

Mem0's memory layer research informed our storage architecture:

- **Two-phase architecture:** Separate extraction (identifying what's important) from storage (how to persist it). We apply this by first generating summaries via LLM, then persisting results to both files and vector DB.

---

## 3. Architectural Decisions

### 3.1 Token-Based Level Selection

**Decision:** Select summarization strategy based on input token count with fixed thresholds.

**Rationale:**

- **Predictable behavior:** Users can anticipate output length based on input size.
- **Efficiency:** Avoid over-processing short content or under-processing long content.

**Thresholds:**

| Level | Token Range | Strategy |
| :--- | :--- | :--- |
| NONE | < 100 | No summarization needed |
| BRIEF | 100-500 | Single sentence |
| STANDARD | 500-3000 | Paragraph |
| DETAILED | 3000-15000 | Chunked + meta-synthesis |
| HIERARCHICAL | > 15000 | L1/L2/L3 tree |

**Trade-off:** Fixed thresholds may not be optimal for all content types, but provide consistent, predictable behavior. Content-type prompts provide domain adaptation within each level.

### 3.2 Hierarchical Summary Structure (L1/L2/L3)

**Decision:** For long content, build a tree of summaries at three levels of granularity.

**Rationale:**

- **Partial eviction:** Inspired by Letta—keep detailed summaries for granular retrieval, compressed summaries for context injection.
- **Flexible retrieval:** Different use cases need different detail levels. RAG queries might want L1 chunks; prompt injection wants L3.
- **Progressive compression:** Each level compresses the previous, achieving high overall compression while preserving structure.

**Structure:**

- **L1 (Chunk Summaries):** Individual summaries of ~3000 token chunks. Preserves local context and specific details. Chunks overlap by ~200 tokens to maintain continuity across boundaries.
- **L2 (Group Summaries):** Summaries of groups of ~5 L1 summaries. Only generated when content exceeds ~5 chunks. Provides mid-level abstraction.
- **L3 (Final Summary):** Single synthesized summary. Used for prompt injection and as prior context for incremental updates.

**Trade-off:** The three-level hierarchy adds complexity but enables efficient retrieval at multiple granularities. For content under 15000 tokens, we skip L2 entirely (DETAILED level uses only L1 + L3).

### 3.3 Semantic Boundary Chunking

**Decision:** Split content on semantic boundaries (paragraphs, then sentences) rather than fixed character counts.

**Rationale:**

- **Coherence preservation:** Splitting mid-sentence or mid-thought loses context and produces poor summaries.
- **Natural units:** Paragraphs and sentences are natural semantic units that humans use to organize thoughts.
- **Overlap for continuity:** The 200-token overlap ensures concepts spanning chunk boundaries aren't lost.

**Fallback chain:**

1. Prefer paragraph boundaries (double newlines)
2. Fall back to sentence boundaries (`.!?` followed by space + capital)
3. Final fallback to character splitting for edge cases (e.g., code blocks without punctuation)

### 3.4 Content-Type Aware Prompts

**Decision:** Use different prompt templates for different content domains.

**Rationale:**

- **Conversations:** Focus on user preferences, decisions, action items—what the user wants and what was agreed.
- **Journals:** Emphasize personal insights, emotional context, growth patterns—the subjective experience.
- **Documents:** Prioritize key findings, methodology, conclusions—the objective content.

A generic summarization prompt loses domain-specific signal. By tailoring prompts, we extract what matters for each use case.

### 3.5 Prior Summary Integration

**Decision:** Always provide the previous summary as context when generating updates.

**Rationale:**

- **Continuity:** New summaries should build on existing context, not start fresh each time.
- **Incremental updates:** Avoid re-summarizing all historical content on every update.
- **Information preservation:** Important information from earlier content persists through the chain of summaries.

The L3 summary from the previous run becomes prior context for the next summarization, allowing information to flow forward through time.

### 3.6 Compression Ratio Tracking

**Decision:** Track and report compression metrics for every summary.

**Rationale:**

- **Transparency:** Users can understand how much information was compressed.
- **Quality monitoring:** Unusual ratios (e.g., output longer than input) may indicate summarization issues.
- **Optimization:** Metrics inform future threshold tuning and quality assessment.

Every `SummaryResult` includes `input_tokens`, `output_tokens`, and `compression_ratio` for observability.

---

## 4. Processing Pipeline

### 4.1 Level Selection

The entry point counts tokens and selects strategy:

1. **Token counting:** Uses tiktoken with model-appropriate encoding. Falls back to character-based estimation (~4 chars/token) if tiktoken unavailable.
2. **Threshold comparison:** Maps token count to `SummaryLevel` enum.
3. **Strategy dispatch:** Calls level-specific handler.

### 4.2 Brief and Standard Levels

For short content (< 3000 tokens):

- Single LLM call with level-appropriate prompt
- Prior summary injected as context if available
- Content-type selection determines prompt variant
- Returns simple `SummaryResult` with no hierarchical structure

### 4.3 Detailed and Hierarchical Levels

For longer content:

1. **Chunking:** Split content into overlapping chunks on semantic boundaries.
2. **Parallel L1 generation:** Summarize each chunk independently. Uses semaphore-controlled concurrency to avoid overwhelming the LLM.
3. **L2 grouping (hierarchical only):** Organize L1s into groups of ~5, summarize each group.
4. **L3 synthesis:** Meta-summarize all L2s (or all L1s for DETAILED level) into final summary.

The parallelism at L1 and L2 levels provides significant speedup for long content while maintaining semantic coherence through the hierarchical structure.

---

## 5. Integration with Memory System

### 5.1 Write Path

The memory system triggers summarization during post-processing:

1. Collect content to summarize (extracted facts, conversation turns)
2. Retrieve existing L3 summary as prior context
3. Call summarizer with content + prior summary + content type
4. Persist results: delete old summaries, write new files, upsert to ChromaDB

### 5.2 Read Path

The memory retrieval system uses summaries for context injection:

- Fetches L3 (final) summary for the conversation
- Injects as prefix to retrieved memories in the prompt
- Provides high-level context that individual memory snippets lack

### 5.3 Storage

Summaries are persisted in two places:

- **Files:** Markdown with YAML front matter under `summaries/L1/`, `L2/`, `L3/` directories. Human-readable, git-trackable.
- **ChromaDB:** Vector embeddings for semantic search. Metadata includes level, compression metrics, timestamps.

---

## 6. Configuration

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `chunk_size` | 3000 | Target tokens per chunk |
| `chunk_overlap` | 200 | Overlap between consecutive chunks |
| `max_concurrent_chunks` | 5 | Parallel LLM calls for chunk summarization |

Level thresholds are constants (100, 500, 3000, 15000 tokens) chosen based on empirical testing.

---

## 7. Error Handling

Summarization follows a fail-fast philosophy:

- **LLM errors:** Propagated as `SummarizationError` rather than silently returning empty results.
- **Empty input:** Returns NONE level immediately (not an error).
- **Encoding errors:** Falls back to character-based token estimation.

The caller (memory system) decides how to handle failures—typically by proceeding without a summary rather than blocking the entire write path.
