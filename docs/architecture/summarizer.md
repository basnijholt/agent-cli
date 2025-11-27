# Agent CLI: Adaptive Summarizer Technical Specification

This document describes the architectural decisions, design rationale, and technical approach for the `agent-cli` adaptive summarization subsystem.

## 1. System Overview

The adaptive summarizer provides **content-aware compression** using a map-reduce approach inspired by LangChain's chains. Rather than applying fixed summarization levels, it dynamically collapses content until it fits within a token budget.

```
Input Content ──▶ Token Count ──▶ Strategy Selection
                                        │
        ┌───────────────────────────────┼─────────────────────┐
        │                               │                     │
   < 100 tokens                  100-500 tokens         > 500 tokens
        │                               │                     │
   No summary                    Brief summary           Map-Reduce
                                (single sentence)     (dynamic collapse)
```

**Design Goals:**

- **Simple algorithm:** Map-reduce with dynamic collapse depth based on actual content.
- **Research-grounded defaults:** chunk_size=2048 (BOOOOKSCORE), token_max=3000 (LangChain).
- **Content-type awareness:** Domain-specific prompts for conversations, journals, documents.

---

## 2. Research Foundations

This section documents what techniques are borrowed from research vs. what is original design.

### 2.1 Borrowed: LangChain Map-Reduce Pattern

**Reference:** LangChain `ReduceDocumentsChain`

LangChain's approach to document summarization uses a simple algorithm:
1. **Map phase:** Split content into chunks, summarize each in parallel
2. **Reduce phase:** If combined summaries exceed `token_max`, recursively collapse until they fit

Key insight: No need for predetermined L1/L2/L3 levels. Dynamic depth based on actual content length. LangChain's default `token_max=3000`.

### 2.2 Borrowed: Chunk Size (BOOOOKSCORE)

**Reference:** arXiv:2310.00785 (ICLR 2024)

BOOOOKSCORE's research on book-length summarization found optimal chunk sizes. Their defaults:
- Chunk size: **2048 tokens** (we use this)
- Max summary length: **900 tokens**

### 2.3 Borrowed: Two-Phase Architecture (Mem0)

**Reference:** arXiv:2504.19413

Mem0's memory layer research informed our storage architecture with a **two-phase approach**: separate extraction (identifying what's important) from storage (how to persist it). We apply this by first generating summaries via LLM, then persisting results to both files and vector DB.

### 2.4 Not Directly Borrowed: Letta's Approach

**Reference:** arXiv:2310.08560

Letta (MemGPT) uses a different paradigm focused on **context window management**:
- Message count thresholds (e.g., 10 messages), not token thresholds
- 30% partial eviction when buffer overflows
- Purpose: fit conversation in LLM context window

Our system has a different purpose (memory compression for storage/retrieval), so our implementation differs significantly.

### 2.5 Original Design (Not Research-Backed)

The following aspects are **original design choices without direct research justification**:

- **Token thresholds (100/500):** The boundaries between NONE/BRIEF/map-reduce were chosen heuristically.
- **L2 group logic for storage:** The intermediate summaries stored as "L2" is for backward compatibility with the storage layer.
- **Content-type prompts:** Domain-specific prompts are original design.

---

## 3. Architectural Decisions

### 3.1 Map-Reduce with Dynamic Collapse

**Decision:** Use LangChain-style map-reduce instead of fixed L1/L2/L3 levels.

**Rationale:**

- **Simpler algorithm:** No need to distinguish STANDARD/DETAILED/HIERARCHICAL.
- **Dynamic depth:** Collapse depth adapts to actual content length.
- **Research-backed:** LangChain's approach is battle-tested.

**Algorithm:**

```python
def map_reduce_summarize(content, token_max=3000):
    if tokens(content) <= token_max:
        return summarize_directly(content)

    # Map: Split and summarize chunks in parallel
    chunks = split_into_chunks(content, chunk_size=2048)
    summaries = [summarize(chunk) for chunk in chunks]

    # Reduce: Recursively collapse until fits
    while total_tokens(summaries) > token_max:
        groups = group_summaries_by_token_max(summaries, token_max)
        summaries = [synthesize(group) for group in groups]

    return final_synthesis(summaries)
```

### 3.2 Token-Based Level Selection (Simplified)

**Decision:** Use three effective levels instead of five.

**Rationale:**

- **Simplicity:** Fewer code paths, easier to understand.
- **Dynamic instead of fixed:** Map-reduce adapts to content, no need for DETAILED vs HIERARCHICAL distinction.

**Effective Levels:**

| Level | Token Range | Strategy |
| :--- | :--- | :--- |
| NONE | < 100 | No summarization needed |
| BRIEF | 100-500 | Single sentence |
| MAP_REDUCE | > 500 | Dynamic collapse until fits token_max |

**Backward Compatibility:** The output still reports STANDARD, DETAILED, or HIERARCHICAL based on collapse depth for storage compatibility.

### 3.3 Research-Backed Defaults

**Decision:** Use values from published research.

| Parameter | Value | Source |
| :--- | :--- | :--- |
| `chunk_size` | 2048 | BOOOOKSCORE |
| `token_max` | 3000 | LangChain |
| `chunk_overlap` | 200 | Original |

### 3.4 Semantic Boundary Chunking

**Decision:** Split content on semantic boundaries (paragraphs, then sentences) rather than fixed character counts.

**Rationale:**

- **Coherence preservation:** Splitting mid-sentence or mid-thought loses context and produces poor summaries.
- **Natural units:** Paragraphs and sentences are natural semantic units that humans use to organize thoughts.
- **Overlap for continuity:** The 200-token overlap ensures concepts spanning chunk boundaries aren't lost.

**Fallback chain:**

1. Prefer paragraph boundaries (double newlines)
2. Fall back to sentence boundaries (`.!?` followed by space + capital)
3. Final fallback to character splitting for edge cases (e.g., code blocks without punctuation)

### 3.5 Content-Type Aware Prompts

**Decision:** Use different prompt templates for different content domains.

**Rationale:**

- **Conversations:** Focus on user preferences, decisions, action items—what the user wants and what was agreed.
- **Journals:** Emphasize personal insights, emotional context, growth patterns—the subjective experience.
- **Documents:** Prioritize key findings, methodology, conclusions—the objective content.

A generic summarization prompt loses domain-specific signal. By tailoring prompts, we extract what matters for each use case.

### 3.6 Prior Summary Integration

**Decision:** Always provide the previous summary as context when generating updates.

**Rationale:**

- **Continuity:** New summaries should build on existing context, not start fresh each time.
- **Incremental updates:** Avoid re-summarizing all historical content on every update.
- **Information preservation:** Important information from earlier content persists through the chain of summaries.

The L3 summary from the previous run becomes prior context for the next summarization, allowing information to flow forward through time.

### 3.7 Compression Ratio Tracking

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
2. **Threshold comparison:** Determines if NONE, BRIEF, or map-reduce.
3. **Strategy dispatch:** Calls appropriate handler.

### 4.2 Brief Level

For short content (100-500 tokens):

- Single LLM call with brief prompt
- Returns simple `SummaryResult` with no hierarchical structure

### 4.3 Map-Reduce Level

For longer content (> 500 tokens):

1. **Check single-chunk:** If content fits in token_max, use content-type aware summary directly.
2. **Map phase:** Split content into overlapping chunks, summarize each in parallel.
3. **Reduce phase:** If combined summaries exceed token_max, group and re-summarize recursively.
4. **Final synthesis:** Combine remaining summaries into final output.

The parallelism in the map phase provides significant speedup for long content while maintaining semantic coherence through the collapse process.

---

## 5. Integration with Memory System

### 5.1 Write Path

The memory system triggers summarization during post-processing:

1. Collect raw conversation turns (user message + assistant message)
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

For backward compatibility, the dynamic collapse levels are mapped to L1/L2/L3 structure:
- First collapse level → L1 (chunk summaries)
- Intermediate levels → L2 (grouped summaries)
- Final output → L3 (synthesis)

---

## 6. Configuration

| Parameter | Default | Source |
| :--- | :--- | :--- |
| `chunk_size` | 2048 | BOOOOKSCORE |
| `token_max` | 3000 | LangChain |
| `chunk_overlap` | 200 | Original |
| `max_concurrent` | 5 | Implementation choice |
| `max_collapse_depth` | 10 | Safety limit |

---

## 7. Error Handling

Summarization follows a fail-fast philosophy:

- **LLM errors:** Propagated as `SummarizationError` or `MapReduceSummarizationError` rather than silently returning empty results.
- **Empty input:** Returns NONE level immediately (not an error).
- **Encoding errors:** Falls back to character-based token estimation.
- **Max depth exceeded:** Warning logged, forces final synthesis even if over token_max.

The caller (memory system) decides how to handle failures—typically by proceeding without a summary rather than blocking the entire write path.

---

## 8. Comparison: Old vs New Approach

| Aspect | Old Approach | New Approach |
| :--- | :--- | :--- |
| Levels | 5 fixed (NONE/BRIEF/STANDARD/DETAILED/HIERARCHICAL) | 3 effective (NONE/BRIEF/MAP_REDUCE) |
| Hierarchy | Fixed L1/L2/L3 structure | Dynamic collapse depth |
| Chunk size | 3000 tokens | 2048 tokens (BOOOOKSCORE) |
| token_max | N/A (fixed levels) | 3000 (LangChain) |
| Complexity | Multiple code paths | Single map-reduce algorithm |
| Research basis | Heuristic | LangChain + BOOOOKSCORE |

---

## 9. Future Improvements

1. **Benchmark against BOOOOKSCORE metrics** for coherence evaluation
2. **Add incremental updating mode** as alternative to hierarchical merging for larger context models
3. **Tune token thresholds empirically** with real-world content
