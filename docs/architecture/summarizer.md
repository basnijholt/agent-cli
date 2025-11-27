# Agent CLI: Adaptive Summarizer Technical Specification

This document describes the architectural decisions, design rationale, and technical approach for the `agent-cli` adaptive summarization subsystem. The design is grounded in research from Letta (partial eviction, middle truncation) and Mem0 (rolling summaries, compression ratios).

## 1. System Overview

The adaptive summarizer provides **content-aware compression** that scales summarization depth with input complexity. Rather than applying a one-size-fits-all approach, it automatically selects the optimal strategy based on token count.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Adaptive Summarization Pipeline                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Input Content ──▶ Token Count ──▶ Level Selection ──▶ Strategy     │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ Level Thresholds:                                           │    │
│  │   < 100 tokens  ──▶ NONE        (no summary needed)         │    │
│  │   100-500       ──▶ BRIEF       (single sentence)           │    │
│  │   500-3000      ──▶ STANDARD    (paragraph)                 │    │
│  │   3000-15000    ──▶ DETAILED    (chunked + meta)            │    │
│  │   > 15000       ──▶ HIERARCHICAL (L1/L2/L3 tree)            │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  Output: SummaryResult with compression metrics                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Design Goals:**

- **Adaptive compression:** Match summarization depth to content complexity.
- **Research-grounded:** Based on proven approaches from Letta and Mem0.
- **Hierarchical structure:** Preserve detail at multiple granularities.
- **Content-type awareness:** Domain-specific prompts for conversations, journals, documents.

---

## 2. Architectural Decisions

### 2.1 Token-Based Level Selection

**Decision:** Select summarization strategy based on input token count with fixed thresholds.

**Rationale:**

- **Predictable behavior:** Users can anticipate output length based on input size.
- **Optimal compression:** Each level targets a specific compression ratio validated by research.
- **Efficiency:** Avoid over-processing short content or under-processing long content.

**Implementation:**

```python
THRESHOLD_NONE = 100       # Below this: no summary needed
THRESHOLD_BRIEF = 500      # 100-500: single sentence (~20% compression)
THRESHOLD_STANDARD = 3000  # 500-3000: paragraph (~12% compression)
THRESHOLD_DETAILED = 15000 # 3000-15000: chunked (~7% compression)
# Above 15000: hierarchical tree structure
```

**Trade-off:** Fixed thresholds may not be optimal for all content types, but provide consistent, predictable behavior.

### 2.2 Hierarchical Summary Structure (L1/L2/L3)

**Decision:** For long content, build a tree of summaries at three levels of granularity.

**Rationale:**

- **Partial eviction:** Inspired by Letta's memory architecture—keep detailed summaries for recent content, compressed summaries for older content.
- **Flexible retrieval:** Different use cases need different detail levels.
- **Progressive compression:** Each level provides ~5x compression over the previous.

**Implementation:**

- **L1 (Chunk Summaries):** Individual summaries of ~3000 token chunks with 200 token overlap.
- **L2 (Group Summaries):** Summaries of groups of ~5 L1 summaries.
- **L3 (Final Summary):** Single synthesized summary of all L2 summaries.

**Storage:**
```text
summaries/
  L1/
    chunk_0.md    # Summary of tokens 0-3000
    chunk_1.md    # Summary of tokens 2800-5800 (overlap)
  L2/
    group_0.md    # Synthesis of chunk_0 through chunk_4
  L3/
    final.md      # Final narrative summary
```

### 2.3 Content-Type Aware Prompts

**Decision:** Use different prompt templates for different content domains.

**Rationale:**

- **Conversations:** Focus on user preferences, decisions, action items.
- **Journals:** Emphasize personal insights, emotional context, growth patterns.
- **Documents:** Prioritize key findings, methodology, conclusions.

**Implementation:**

```python
def get_prompt_for_content_type(content_type: str) -> str:
    match content_type:
        case "conversation": return CONVERSATION_PROMPT
        case "journal": return JOURNAL_PROMPT
        case "document": return DOCUMENT_PROMPT
        case _: return STANDARD_PROMPT
```

### 2.4 Prior Summary Integration

**Decision:** Always provide the previous summary as context when updating.

**Rationale:**

- **Continuity:** New summaries should build on existing context, not replace it.
- **Incremental updates:** Avoid re-summarizing all content on every update.
- **Context preservation:** Important information from earlier content persists.

**Implementation:**

- The `prior_summary` parameter is passed through the entire pipeline.
- `ROLLING_PROMPT` specifically handles integrating new facts with existing summaries.
- For hierarchical summaries, only the L3 summary is used as prior context.

### 2.5 Compression Ratio Tracking

**Decision:** Track and report compression metrics for every summary.

**Rationale:**

- **Transparency:** Users can understand how much information was compressed.
- **Quality monitoring:** Unusual ratios may indicate summarization issues.
- **Optimization:** Metrics inform future threshold tuning.

**Implementation:**

```python
@dataclass
class SummaryResult:
    level: SummaryLevel
    summary: str | None
    hierarchical: HierarchicalSummary | None
    input_tokens: int
    output_tokens: int
    compression_ratio: float  # output/input (lower = more compression)
```

---

## 3. Data Model

### 3.1 Summary Levels

| Level | Token Range | Target Compression | Strategy |
| :--- | :--- | :--- | :--- |
| `NONE` | < 100 | N/A | No summarization |
| `BRIEF` | 100-500 | ~20% | Single sentence |
| `STANDARD` | 500-3000 | ~12% | Paragraph |
| `DETAILED` | 3000-15000 | ~7% | Chunked + meta |
| `HIERARCHICAL` | > 15000 | ~3-5% | L1/L2/L3 tree |

### 3.2 Hierarchical Summary Structure

```python
class ChunkSummary(BaseModel):
    chunk_index: int          # Position in original content
    content: str              # The summarized text
    token_count: int          # Tokens in this summary
    source_tokens: int        # Tokens in source chunk
    parent_group: int | None  # L2 group this belongs to

class HierarchicalSummary(BaseModel):
    l1_summaries: list[ChunkSummary]  # Individual chunk summaries
    l2_summaries: list[str]           # Group summaries
    l3_summary: str                   # Final synthesis
    chunk_size: int = 3000            # Tokens per chunk
    chunk_overlap: int = 200          # Overlap between chunks
```

### 3.3 Storage Metadata (ChromaDB)

Summaries are stored with rich metadata for retrieval and management:

| Field | L1 | L2 | L3 | Description |
| :--- | :---: | :---: | :---: | :--- |
| `id` | ✓ | ✓ | ✓ | `{conversation_id}:summary:L{n}:{index}` |
| `conversation_id` | ✓ | ✓ | ✓ | Scope key |
| `role` | ✓ | ✓ | ✓ | Always `"summary"` |
| `level` | ✓ | ✓ | ✓ | 1, 2, or 3 |
| `chunk_index` | ✓ | | | Position in L1 sequence |
| `group_index` | | ✓ | | Position in L2 sequence |
| `parent_group` | ✓ | | | Which L2 group owns this L1 |
| `is_final` | | | ✓ | Marks the top-level summary |
| `summary_level` | | | ✓ | Name of SummaryLevel enum |
| `input_tokens` | | | ✓ | Original content token count |
| `output_tokens` | | | ✓ | Total summary token count |
| `compression_ratio` | | | ✓ | Output/input ratio |
| `created_at` | ✓ | ✓ | ✓ | ISO 8601 timestamp |

### 3.4 File Format

Summary files use Markdown with YAML front matter:

```markdown
---
id: "journal:summary:L3:final"
conversation_id: "journal"
role: "summary"
level: 3
is_final: true
summary_level: "STANDARD"
input_tokens: 1500
output_tokens: 180
compression_ratio: 0.12
created_at: "2025-01-15T10:30:00Z"
---

The user has been exploring adaptive summarization techniques...
```

---

## 4. Processing Pipeline

### 4.1 Main Entry Point

```python
async def summarize(
    content: str,
    config: SummarizerConfig,
    prior_summary: str | None = None,
    content_type: str = "general",
) -> SummaryResult
```

### 4.2 Level Selection Flow

```
Input Content
     │
     ▼
┌─────────────┐
│ Count Tokens│ (tiktoken, cl100k_base)
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ determine_level(token_count) -> Level   │
│                                         │
│   < 100  ──▶ NONE                       │
│   < 500  ──▶ BRIEF                      │
│   < 3000 ──▶ STANDARD                   │
│   < 15000 ──▶ DETAILED                  │
│   else   ──▶ HIERARCHICAL               │
└──────┬──────────────────────────────────┘
       │
       ▼
   Execute level-specific strategy
```

### 4.3 Strategy Execution by Level

#### NONE Level
- **Action:** Return immediately with no summary.
- **Output:** `SummaryResult(level=NONE, summary=None, compression_ratio=1.0)`

#### BRIEF Level
- **Prompt:** `BRIEF_PROMPT` - distill to single sentence.
- **LLM Call:** Single generation with low max_tokens.
- **Output:** One-sentence summary.

#### STANDARD Level
- **Prompt:** `STANDARD_PROMPT` with optional prior summary context.
- **LLM Call:** Single generation.
- **Output:** Paragraph-length summary.

#### DETAILED Level
1. **Chunk:** Split content into ~3000 token chunks with 200 token overlap.
2. **Parallel L1:** Generate summary for each chunk using `CHUNK_PROMPT`.
3. **Meta-synthesis:** Combine L1 summaries using `META_PROMPT`.
4. **Output:** `HierarchicalSummary` with L1s and L3 (no L2 needed for this size).

#### HIERARCHICAL Level
1. **Chunk:** Split into ~3000 token chunks with overlap.
2. **Parallel L1:** Generate chunk summaries.
3. **Group:** Organize L1s into groups of ~5.
4. **Parallel L2:** Summarize each group.
5. **L3 Synthesis:** Final meta-summary of all L2s.
6. **Output:** Full `HierarchicalSummary` tree.

### 4.4 Chunking Algorithm

```python
def chunk_text(
    text: str,
    chunk_size: int = 3000,
    overlap: int = 200,
) -> list[str]:
    """Split text into overlapping chunks on paragraph boundaries."""
```

**Strategy:**

1. **Paragraph-first:** Try to split on double newlines.
2. **Sentence fallback:** If paragraph exceeds chunk_size, split on sentence boundaries.
3. **Character fallback:** For very long sentences (e.g., code), use character splitting.
4. **Overlap handling:** Each chunk starts with the last `overlap` tokens of the previous.

### 4.5 Middle Truncation (Utility)

For handling very large inputs that could exceed context windows:

```python
def middle_truncate(
    text: str,
    budget_chars: int,
    head_frac: float = 0.3,
    tail_frac: float = 0.3,
) -> tuple[str, int]:
    """Keep head and tail, remove middle (least likely to contain key info)."""
```

**Rationale:** Research shows that important information clusters at beginnings (introductions, key points) and endings (conclusions, action items). Useful when summarizing very long conversations that may contain pasted codebases.

---

## 5. Prompt Specifications

### 5.1 Brief Summary (`BRIEF_PROMPT`)

```
Distill the following content into a single, comprehensive sentence
that captures the essential meaning:

{content}

Summary (one sentence):
```

### 5.2 Standard Summary (`STANDARD_PROMPT`)

```
Summarize the following content in a concise paragraph.
{prior_context}
Focus on key information, decisions, and actionable insights.

Content:
{content}

Summary:
```

### 5.3 Chunk Summary (`CHUNK_PROMPT`)

```
Summarize this section of a larger document.
Preserve specific details, names, and numbers that may be important.

Section {chunk_index} of {total_chunks}:
{content}

Section summary:
```

### 5.4 Meta Summary (`META_PROMPT`)

```
Synthesize these section summaries into a coherent narrative.
Maintain logical flow and preserve the most important information.

Section Summaries:
{summaries}

Synthesized Summary:
```

### 5.5 Content-Type Prompts

All content-type prompts include `{prior_context}` for rolling summary continuity.

**Conversation:**
```
Summarize this conversation focusing on:
- User preferences and decisions
- Action items and commitments
- Key topics discussed
```

**Journal:**
```
Summarize this journal entry focusing on:
- Personal insights and reflections
- Emotional context and growth
- Goals and intentions
```

**Document:**
```
Summarize this document focusing on:
- Key findings and conclusions
- Methodology and approach
- Recommendations and implications
```

---

## 6. Integration with Memory System

### 6.1 Entry Point

The memory system calls the summarizer via `_ingest.summarize_content()`:

```python
async def summarize_content(
    content: str,
    prior_summary: str | None = None,
    content_type: str = "general",
    openai_base_url: str,
    api_key: str | None,
    model: str,
) -> SummaryResult
```

### 6.2 Storage Flow

```
summarize_content()
       │
       ▼
SummaryResult
       │
       ▼
store_adaptive_summary()
       │
       ├──▶ persist_hierarchical_summary()
       │         │
       │         ├──▶ Delete old summaries (L1, L2, L3)
       │         ├──▶ Write new summary files
       │         └──▶ Upsert to ChromaDB
       │
       └──▶ Return stored IDs
```

### 6.3 Retrieval Integration

The memory retrieval system uses `get_final_summary()` to fetch the L3 summary:

```python
def get_final_summary(
    collection: Collection,
    conversation_id: str,
) -> StoredMemory | None:
    """Retrieve the L3 final summary for injection into prompts."""
```

---

## 7. Configuration Reference

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `openai_base_url` | *required* | Base URL for LLM API |
| `model` | *required* | Model ID for summarization |
| `api_key` | `None` | API key (optional for local models) |
| `chunk_size` | `3000` | Tokens per chunk for hierarchical |
| `chunk_overlap` | `200` | Token overlap between chunks |

### 7.1 Level Thresholds (Constants)

| Constant | Value | Description |
| :--- | :--- | :--- |
| `THRESHOLD_NONE` | 100 | Below: no summary |
| `THRESHOLD_BRIEF` | 500 | Below: single sentence |
| `THRESHOLD_STANDARD` | 3000 | Below: paragraph |
| `THRESHOLD_DETAILED` | 15000 | Below: chunked |

---

## 8. Error Handling

### 8.1 Fail-Fast Philosophy

Errors are propagated rather than hidden behind fallbacks:

| Error | Behavior |
| :--- | :--- |
| LLM timeout | Raises `SummarizationError` |
| LLM error | Raises `SummarizationError` |
| Token counting failure | Falls back to `cl100k_base` encoding |

### 8.2 Validation

- **Empty content:** Returns NONE level immediately.
- **Whitespace-only:** Returns NONE level.
- **Invalid compression ratio:** Clamped to [0.0, 1.0].

---

## 9. Performance Considerations

### 9.1 Token Counting

- Uses `tiktoken` with `cl100k_base` encoding (GPT-4 tokenizer).
- Caches tokenizer instance for efficiency.
- Falls back to character-based estimation if tiktoken unavailable.

### 9.2 Parallel Processing

For DETAILED and HIERARCHICAL levels:
- L1 chunk summaries can be generated in parallel.
- L2 group summaries can be generated in parallel.
- Only L3 synthesis requires sequential processing.

### 9.3 Caching

- Token counts are computed once per content string.
- Prompt templates are loaded once at module import.
- ChromaDB connection is reused across operations.

---

## 10. Comparison with Alternative Approaches

| Aspect | Adaptive Summarizer | Rolling Summary | Fixed Chunking |
| :--- | :--- | :--- | :--- |
| **Compression** | 3-20% (varies by level) | ~15% fixed | ~10% fixed |
| **Detail preservation** | Hierarchical (L1/L2/L3) | Single level | Single level |
| **Context awareness** | Content-type prompts | Generic | Generic |
| **Efficiency** | Skip short content | Always summarize | Always chunk |
| **Research basis** | Letta + Mem0 | Mem0 only | None |

---

## 11. Future Enhancements

- **Semantic chunking:** Split on topic boundaries rather than token counts.
- **Incremental L1 updates:** Only re-summarize changed chunks.
- **Quality scoring:** Evaluate summary quality and trigger re-summarization.
- **User feedback loop:** Learn preferred compression ratios per user.
