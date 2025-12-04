# Agent CLI: Adaptive Summarizer Technical Specification

This document describes the architectural decisions, design rationale, and technical approach for the `agent-cli` adaptive summarization subsystem.

## 1. System Overview

The adaptive summarizer provides **content-aware compression** using a map-reduce approach inspired by LangChain's chains. It compresses content to fit within a specified token budget using a simple algorithm:

```
Input Content ──▶ Token Count ──▶ Compare to Target
                                        │
                ┌───────────────────────┴───────────────────────┐
                │                                               │
          Fits target                                    Exceeds target
                │                                               │
          Return as-is                                   Map-Reduce
          (no LLM call)                               (dynamic collapse)
```

**Design Goals:**

- **Maximum simplicity:** Single entry point with straightforward logic.
- **Flexible targeting:** Specify absolute token count or relative compression ratio.
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

### 2.3 Original Design (Not Research-Backed)

The following aspects are **original design choices without direct research justification**:

- **Content-type prompts:** Domain-specific prompts are original design.
- **Target ratio parameter:** The option to specify compression as a percentage is a convenience feature.

---

## 3. Architectural Decisions

### 3.1 Simple Target-Based Logic

**Decision:** Use a simple "fits? return : compress" algorithm.

**Rationale:**

- **Minimal complexity:** No level selection logic, threshold management, or multiple code paths.
- **Clear semantics:** If content fits the target, return it unchanged. Otherwise, compress.
- **Flexible targeting:** Users can specify exact token counts or relative ratios.

**Algorithm:**

```python
async def summarize(
    content: str,
    config: SummarizerConfig,
    *,
    target_tokens: int | None = None,   # Absolute limit
    target_ratio: float | None = None,  # e.g., 0.2 = compress to 20%
) -> SummaryResult:
    input_tokens = count_tokens(content)

    # Determine target
    if target_ratio is not None:
        target = max(1, int(input_tokens * target_ratio))
    elif target_tokens is not None:
        target = target_tokens
    else:
        target = config.token_max  # Default: 3000

    # Already fits? Return as-is (no LLM call)
    if input_tokens <= target:
        return SummaryResult(summary=content, ...)

    # Compress using map-reduce
    return await map_reduce_summarize(content, config, target)
```

### 3.2 Map-Reduce with Dynamic Collapse

**Decision:** Use LangChain-style map-reduce for all compression.

**Rationale:**

- **Single algorithm:** One code path handles all content sizes.
- **Dynamic depth:** Collapse depth adapts to actual content length.
- **Research-backed:** LangChain's approach is battle-tested.

**Algorithm:**

```python
async def map_reduce_summarize(content, config, target):
    # Map: Split and summarize chunks in parallel
    chunks = chunk_text(content, chunk_size=2048)
    summaries = await parallel_summarize(chunks)

    # Reduce: Recursively collapse until fits target
    while total_tokens(summaries) > target:
        groups = group_by_token_limit(summaries, target)
        summaries = await parallel_synthesize(groups)

    return final_synthesis(summaries)
```

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

### 4.1 Entry Point

The entry point (`summarize()`) implements simple logic:

1. **Token counting:** Uses tiktoken with model-appropriate encoding. Falls back to character-based estimation (~4 chars/token) if tiktoken unavailable.
2. **Target calculation:** Determines target from `target_tokens`, `target_ratio`, or default `token_max`.
3. **Fit check:** If content fits target, return as-is.
4. **Compression:** Call map-reduce if content exceeds target.

### 4.2 Single-Chunk Content

For content that fits within `chunk_size` but exceeds target:

- Single LLM call with content-type aware prompt
- Returns `SummaryResult` with compressed summary

### 4.3 Multi-Chunk Content

For larger content (> chunk_size tokens):

1. **Map phase:** Split content into overlapping chunks, summarize each in parallel.
2. **Reduce phase:** If combined summaries exceed target, group and re-summarize recursively.
3. **Final synthesis:** Combine remaining summaries into final output.

The `collapse_depth` field in the result indicates how many reduce iterations were needed.

---

## 5. Data Models

### 5.1 SummaryResult

```python
class SummaryResult(BaseModel):
    summary: str | None      # None if content was empty
    input_tokens: int
    output_tokens: int
    compression_ratio: float  # 0.0-1.0
    collapse_depth: int       # 0 = no collapse needed
    created_at: datetime
```

### 5.2 SummarizerConfig

```python
@dataclass
class SummarizerConfig:
    openai_base_url: str
    model: str
    api_key: str | None = None
    chunk_size: int = 2048      # BOOOOKSCORE
    token_max: int = 3000       # LangChain (default target)
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
        "input_tokens": 1500,
        "output_tokens": 150,
        "compression_ratio": 0.1,
        "collapse_depth": 1,
        "created_at": "2024-01-15T10:30:00Z",
        "is_final": True,
    },
}
```

---

## 7. Error Handling

Summarization follows a fail-fast philosophy:

- **LLM errors:** Propagated as `SummarizationError` (base class for all summarization errors).
- **Empty input:** Returns result with `summary=None` immediately (not an error).
- **Encoding errors:** Falls back to character-based token estimation.
- **Max depth exceeded:** Warning logged, forces final synthesis even if over target.

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

## 9. Usage Examples

### Basic Usage

```python
from agent_cli.summarizer import SummarizerConfig, summarize

config = SummarizerConfig(
    openai_base_url="http://localhost:11434/v1",
    model="llama3.1:8b",
)

# Default: compress to fit 3000 tokens
result = await summarize(content, config)

# Compress to specific token count
result = await summarize(content, config, target_tokens=500)

# Compress to 20% of original size
result = await summarize(content, config, target_ratio=0.2)

# With content type for better prompts
result = await summarize(
    content,
    config,
    target_tokens=500,
    content_type="conversation",
)
```

---

## 10. Limitations and Trade-offs

### 10.1 Fact Preservation

Summarization is inherently lossy. Specific facts (dates, numbers, names) are often dropped in favor of thematic content. If your use case requires fact retrieval:

- Store original content alongside summaries
- Use fact extraction instead of summarization
- Use RAG to retrieve original chunks

### 10.2 No Intermediate Summaries

Unlike hierarchical approaches, map-reduce only stores the final summary. Intermediate chunk summaries are discarded after synthesis. This simplifies storage but removes granular access.

---

## 11. Future Improvements

1. **Benchmark against BOOOOKSCORE metrics** for coherence evaluation
2. **Add fact extraction mode** for use cases requiring specific detail preservation
3. **Streaming support** for real-time summarization feedback
