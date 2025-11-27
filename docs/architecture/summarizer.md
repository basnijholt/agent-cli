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

Key insight: No need for predetermined levels. Dynamic depth based on actual content length. LangChain's default `token_max=3000`.

### 2.2 Borrowed: Chunk Size (BOOOOKSCORE)

**Reference:** arXiv:2310.00785 (ICLR 2024)

BOOOOKSCORE's research on book-length summarization found optimal chunk sizes. Their defaults:
- Chunk size: **2048 tokens** (we use this)
- Max summary length: **900 tokens**

### 2.3 Borrowed: Two-Phase Architecture (Mem0)

**Reference:** arXiv:2504.19413

Mem0's memory layer research informed our storage architecture with a **two-phase approach**: separate extraction (identifying what's important) from storage (how to persist it). We apply this by first generating summaries via LLM, then persisting results to storage.

### 2.4 Original Design (Not Research-Backed)

The following aspects are **original design choices without direct research justification**:

- **Token thresholds (100/500):** The boundaries between NONE/BRIEF/MAP_REDUCE were chosen heuristically.
- **Content-type prompts:** Domain-specific prompts are original design.

---

## 3. Architectural Decisions

### 3.1 Map-Reduce with Dynamic Collapse

**Decision:** Use LangChain-style map-reduce instead of fixed hierarchy.

**Rationale:**

- **Simpler algorithm:** Single code path handles all content sizes.
- **Dynamic depth:** Collapse depth adapts to actual content length.
- **Research-backed:** LangChain's approach is battle-tested.

**Algorithm:**

```python
async def map_reduce_summarize(content, config):
    # Map: Split and summarize chunks in parallel
    chunks = chunk_text(content, chunk_size=2048)
    summaries = await parallel_summarize(chunks)

    # Reduce: Recursively collapse until fits token_max
    while total_tokens(summaries) > config.token_max:
        groups = group_by_token_limit(summaries, config.token_max)
        summaries = await parallel_synthesize(groups)

    return final_synthesis(summaries)
```

### 3.2 Three-Level Strategy

**Decision:** Use three levels based on token count.

| Level | Token Range | Strategy |
| :--- | :--- | :--- |
| NONE | < 100 | No summarization needed |
| BRIEF | 100-500 | Single sentence |
| MAP_REDUCE | >= 500 | Dynamic collapse until fits token_max |

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

- **Coherence preservation:** Splitting mid-sentence loses context.
- **Natural units:** Paragraphs and sentences are natural semantic units.
- **Overlap for continuity:** The 200-token overlap ensures concepts spanning chunk boundaries aren't lost.

**Fallback chain:**

1. Prefer paragraph boundaries (double newlines)
2. Fall back to sentence boundaries (`.!?` followed by space + capital)
3. Final fallback to word-based splitting

### 3.5 Content-Type Aware Prompts

**Decision:** Use different prompt templates for different content domains.

**Rationale:**

- **Conversations:** Focus on user preferences, decisions, action items.
- **Journals:** Emphasize personal insights, emotional context, growth patterns.
- **Documents:** Prioritize key findings, methodology, conclusions.

A generic summarization prompt loses domain-specific signal.

### 3.6 Prior Summary Integration

**Decision:** Provide the previous summary as context when generating updates.

**Rationale:**

- **Continuity:** New summaries build on existing context.
- **Incremental updates:** Avoid re-summarizing all historical content.
- **Information preservation:** Important information persists through the chain.

### 3.7 Compression Ratio Tracking

**Decision:** Track and report compression metrics for every summary.

Every `SummaryResult` includes `input_tokens`, `output_tokens`, `compression_ratio`, and `collapse_depth` for observability.

---

## 4. Processing Pipeline

### 4.1 Level Selection

The entry point (`summarize()`) counts tokens and selects strategy:

1. **Token counting:** Uses tiktoken with model-appropriate encoding. Falls back to character-based estimation (~4 chars/token) if tiktoken unavailable.
2. **Threshold comparison:** Determines NONE, BRIEF, or MAP_REDUCE.
3. **Strategy dispatch:** Calls appropriate handler.

### 4.2 Brief Level

For short content (100-500 tokens):

- Single LLM call with brief prompt
- Returns `SummaryResult` with single-sentence summary

### 4.3 Map-Reduce Level

For longer content (>= 500 tokens):

1. **Check single-chunk:** If content fits in token_max, use content-type aware summary directly.
2. **Map phase:** Split content into overlapping chunks, summarize each in parallel.
3. **Reduce phase:** If combined summaries exceed token_max, group and re-summarize recursively.
4. **Final synthesis:** Combine remaining summaries into final output.

The `collapse_depth` field in the result indicates how many reduce iterations were needed.

---

## 5. Data Models

### 5.1 SummaryLevel

```python
class SummaryLevel(IntEnum):
    NONE = 0       # < 100 tokens
    BRIEF = 1      # 100-500 tokens
    MAP_REDUCE = 2 # >= 500 tokens
```

### 5.2 SummaryResult

```python
class SummaryResult(BaseModel):
    level: SummaryLevel
    summary: str | None
    input_tokens: int
    output_tokens: int
    compression_ratio: float
    collapse_depth: int  # 0 = no collapse needed
    created_at: datetime
```

### 5.3 SummarizerConfig

```python
@dataclass
class SummarizerConfig:
    openai_base_url: str
    model: str
    api_key: str | None = None
    chunk_size: int = 2048      # BOOOOKSCORE
    token_max: int = 3000       # LangChain
    chunk_overlap: int = 200
    max_concurrent_chunks: int = 5
    timeout: float = 60.0
```

---

## 6. Integration with Memory System

### 6.1 Write Path

The memory system triggers summarization during post-processing:

1. Collect raw conversation turns
2. Retrieve existing summary as prior context
3. Call summarizer with content + prior summary + content type
4. Persist result to storage

### 6.2 Read Path

The memory retrieval system uses summaries for context injection:

- Fetches summary for the conversation
- Injects as prefix to retrieved memories
- Provides high-level context that individual snippets lack

### 6.3 Storage

Summaries are stored with metadata:

```python
{
    "id": "{conversation_id}:summary",
    "content": summary_text,
    "metadata": {
        "conversation_id": conversation_id,
        "role": "summary",
        "summary_level": "MAP_REDUCE",
        "input_tokens": 1500,
        "output_tokens": 150,
        "compression_ratio": 0.1,
        "collapse_depth": 1,
        "created_at": "2024-01-15T10:30:00Z",
    },
}
```

---

## 7. Error Handling

Summarization follows a fail-fast philosophy:

- **LLM errors:** Propagated as `SummarizationError` (base class for all summarization errors).
- **Empty input:** Returns NONE level immediately (not an error).
- **Encoding errors:** Falls back to character-based token estimation.
- **Max depth exceeded:** Warning logged, forces final synthesis even if over token_max.

The caller decides how to handle failures—typically by proceeding without a summary rather than blocking the entire operation.

---

## 8. Configuration

| Parameter | Default | Source |
| :--- | :--- | :--- |
| `chunk_size` | 2048 | BOOOOKSCORE |
| `token_max` | 3000 | LangChain |
| `chunk_overlap` | 200 | Original |
| `max_concurrent` | 5 | Implementation choice |
| `max_collapse_depth` | 10 | Safety limit |

---

## 9. Limitations and Trade-offs

### 9.1 Fact Preservation

Summarization is inherently lossy. Specific facts (dates, numbers, names) are often dropped in favor of thematic content. If your use case requires fact retrieval:

- Store original content alongside summaries
- Use fact extraction instead of summarization
- Use RAG to retrieve original chunks

### 9.2 No Intermediate Summaries

Unlike hierarchical approaches, map-reduce only stores the final summary. Intermediate chunk summaries are discarded after synthesis. This simplifies storage but removes granular access.

### 9.3 Fixed Thresholds

The 100/500 token thresholds are heuristic. They may need tuning for specific domains or languages.

---

## 10. Future Improvements

1. **Benchmark against BOOOOKSCORE metrics** for coherence evaluation
2. **Tune token thresholds empirically** with real-world content
3. **Add fact extraction mode** for use cases requiring specific detail preservation
