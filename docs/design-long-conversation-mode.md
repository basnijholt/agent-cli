# Long Conversation Mode: Design Document

## Overview

A new mode for `agent-cli memory proxy` that maintains a single, continuous conversation with intelligent compression, optimized for 100-200k token context windows.

**Key insight**: User input is precious and hard to summarize without loss. LLM output is verbose and derivable. Compress asymmetrically.

## Motivation

Current memory system (`memory proxy`):
- Extracts discrete facts from conversations
- Stores in vector DB, retrieves by semantic similarity
- Treats user and LLM text equally for compression
- Optimized for: many short conversations, cross-conversation retrieval

New mode targets a different use case:
- Single long-running conversation (days/weeks/months)
- LLM learns about user over time
- Full context utilization (100-200k tokens)
- Preserve user intent, compress LLM verbosity

## Integration Point

Add `--long-conversation` flag to `memory proxy`:

```bash
# Current behavior (fact extraction + semantic retrieval)
agent-cli memory proxy --memory-path ./memory_db

# New mode (continuous conversation with asymmetric compression)
agent-cli memory proxy --memory-path ./memory_db --long-conversation
```

Both modes share:
- Same FastAPI proxy infrastructure
- Same storage directory structure
- Same upstream LLM forwarding

They differ in:
- How context is built for each request
- What gets compressed and when
- How repetition is handled

## Architecture

### Current Flow (`memory proxy`)

```
Request → Extract user query
        → Semantic search in ChromaDB
        → Retrieve top-k facts + summary
        → Inject into prompt
        → Forward to LLM
        → Extract facts from response (background)
        → Store new facts
```

### Long Conversation Flow

```
Request → Append to conversation buffer
        → Check if compression needed (approaching context limit)
        → If yes: compress older segments (asymmetrically)
        → Detect repetition in new content
        → Build full context: compressed history + raw recent
        → Forward to LLM
        → Append response to buffer
```

## Data Model

### Conversation Segment

```python
@dataclass
class Segment:
    """A single turn in the conversation."""
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime

    # Token accounting
    original_tokens: int
    current_tokens: int  # After compression

    # Compression state
    state: Literal["raw", "summarized", "reference"]

    # For reference-type (deduplicated) segments
    refers_to: str | None = None  # ID of original segment
    diff: str | None = None       # What changed from original

    # Content fingerprint for dedup
    content_hash: str = ""
```

### Conversation Store

```python
@dataclass
class LongConversation:
    """Full conversation with compression metadata."""
    id: str
    segments: list[Segment]

    # Budget tracking
    target_context_tokens: int = 150_000  # Leave room for response
    current_total_tokens: int = 0

    # Compression thresholds
    compress_threshold: float = 0.8  # Start compressing at 80% of target
    raw_recent_tokens: int = 40_000  # Always keep recent N tokens raw
```

## Compression Strategy

### Tiered Compression

| Content | Recent | Older | Very Old |
|---------|--------|-------|----------|
| **User messages** | Raw | Deduplicated | Light summary (preserve quotes) |
| **LLM messages** | Raw | Summarized to conclusions | Bullet points only |

### Asymmetric Ratios

```python
COMPRESSION_CONFIG = {
    "user": {
        "recent_turns": 20,           # Keep last N user turns raw
        "summary_target_ratio": 0.7,  # Compress to 70% (gentle)
        "preserve_quotes": True,      # Keep exact user phrasing
        "preserve_code": True,        # Never summarize code blocks
    },
    "assistant": {
        "recent_turns": 10,           # Keep last N assistant turns raw
        "summary_target_ratio": 0.2,  # Compress to 20% (aggressive)
        "keep_decisions": True,       # Preserve: "I decided to...", "I'll use..."
        "keep_conclusions": True,     # Preserve final answers
    },
}
```

### Compression Triggers

```python
def should_compress(conversation: LongConversation) -> bool:
    """Check if compression is needed."""
    usage_ratio = conversation.current_total_tokens / conversation.target_context_tokens
    return usage_ratio >= conversation.compress_threshold

def select_segments_to_compress(conversation: LongConversation) -> list[Segment]:
    """Select oldest non-raw segments, preferring LLM content."""
    candidates = []
    for seg in conversation.segments:
        if seg.state != "raw":
            continue
        # Skip recent segments
        if is_recent(seg, conversation):
            continue
        candidates.append(seg)

    # Sort: LLM messages first (compress those more aggressively)
    candidates.sort(key=lambda s: (s.role == "user", s.timestamp))
    return candidates
```

## Repetition Detection

### Code Block Deduplication

Users frequently paste the same code with minor changes:

```python
def detect_code_repetition(
    new_content: str,
    history: list[Segment],
) -> RepetitionResult | None:
    """Find near-duplicate code blocks."""
    new_blocks = extract_code_blocks(new_content)

    for block in new_blocks:
        block_hash = hash_code_block(block)

        for seg in history:
            if seg.role != "user":
                continue

            for hist_block in extract_code_blocks(seg.content):
                similarity = compute_similarity(block, hist_block)

                if similarity > 0.85:  # Near-duplicate
                    diff = compute_unified_diff(hist_block, block)
                    diff_size = len(diff)
                    original_size = len(block)

                    if diff_size < original_size * 0.3:
                        return RepetitionResult(
                            original_segment_id=seg.id,
                            diff=diff,
                            saved_tokens=count_tokens(block) - count_tokens(diff),
                        )

    return None
```

### Replacement Format

When repetition is detected, store:

```markdown
[Code block similar to turn #42, with these changes:]
```diff
@@ -45,3 +45,5 @@
     def process(self):
-        return self.data
+        validated = self.validate()
+        return self.transform(validated)
```
```

## Context Building

### Building the Prompt

```python
def build_context(
    conversation: LongConversation,
    new_message: str,
    token_budget: int,
) -> list[Message]:
    """Build full context for LLM request, enforcing token budget."""
    messages = []

    # 1. System message with conversation metadata (required)
    system_msg = {
        "role": "system",
        "content": build_system_prompt(conversation),
    }
    messages.append(system_msg)

    # 2. New user message (required, reserve space)
    new_user_msg = {"role": "user", "content": new_message}
    reserved_tokens = count_tokens(system_msg) + count_tokens(new_user_msg)

    # 3. Recent raw conversation (high priority)
    recent_segments = get_recent_segments(conversation)
    recent_messages = [
        {"role": seg.role, "content": seg.content}
        for seg in recent_segments
    ]

    # 4. Compressed older history (lower priority, can be trimmed)
    compressed_history = render_compressed_segments(
        conversation.segments,
        exclude_recent=True,
    )
    history_msg = None
    if compressed_history:
        history_msg = {
            "role": "system",
            "content": f"Previous conversation (summarized):\n{compressed_history}",
        }

    # 5. Enforce token budget by trimming older content first
    available = token_budget - reserved_tokens
    recent_tokens = sum(count_tokens(m) for m in recent_messages)
    history_tokens = count_tokens(history_msg) if history_msg else 0

    if recent_tokens + history_tokens > available:
        # Drop summarized history first
        if history_tokens > 0 and recent_tokens <= available:
            history_msg = None
        else:
            # Trim oldest recent messages until we fit
            while recent_messages and recent_tokens > available:
                dropped = recent_messages.pop(0)
                recent_tokens -= count_tokens(dropped)

    # 6. Assemble final message list
    if history_msg:
        messages.append(history_msg)
    messages.extend(recent_messages)
    messages.append(new_user_msg)

    return messages
```

## Storage

### File Structure

```
memory_db/
├── conversations/
│   └── {conversation_id}/
│       ├── segments/
│       │   ├── 0001_user_2024-01-15T10:30:00.md
│       │   ├── 0002_assistant_2024-01-15T10:30:15.md
│       │   └── ...
│       ├── compressed/
│       │   ├── batch_0001-0050.md  # Compressed older segments
│       │   └── ...
│       └── metadata.json
└── index/  # ChromaDB (optional, for hybrid retrieval)
```

### Segment File Format

```markdown
---
id: seg_abc123
role: user
timestamp: 2024-01-15T10:30:00Z
original_tokens: 450
current_tokens: 450
state: raw
content_hash: sha256:abcd1234...
---

Here's the updated module with the fix for the race condition:

```python
class ConnectionPool:
    ...
```
```

## CLI Interface

### New Flags

```python
@memory_app.command("proxy")
def memory_proxy(
    # ... existing flags ...

    # Long conversation mode
    long_conversation: bool = typer.Option(
        False,
        "--long-conversation/--no-long-conversation",
        help="Enable long conversation mode with asymmetric compression.",
        rich_help_panel="Conversation Mode",
    ),
    context_budget: int = typer.Option(
        150_000,
        "--context-budget",
        help="Target context window size in tokens (long-conversation mode).",
        rich_help_panel="Conversation Mode",
    ),
    compress_threshold: float = typer.Option(
        0.8,
        "--compress-threshold",
        help="Start compression when context reaches this fraction of budget.",
        rich_help_panel="Conversation Mode",
    ),
    raw_recent_tokens: int = typer.Option(
        40_000,
        "--raw-recent-tokens",
        help="Always keep this many recent tokens uncompressed.",
        rich_help_panel="Conversation Mode",
    ),
) -> None:
```

### Example Usage

```bash
# Start with 200k context budget, compress at 80%
agent-cli memory proxy \
    --long-conversation \
    --context-budget 200000 \
    --compress-threshold 0.8 \
    --raw-recent-tokens 50000

# Use with Claude (which has 200k context)
agent-cli memory proxy \
    --long-conversation \
    --openai-base-url https://api.anthropic.com/v1 \
    --context-budget 180000
```

## Implementation Phases

### Phase 1: Basic Long Conversation Storage
- [ ] `Segment` and `LongConversation` data models
- [ ] File-based persistence (segments as markdown files)
- [ ] Basic context building (no compression yet)
- [ ] New `--long-conversation` flag

### Phase 2: Asymmetric Compression
- [ ] Token counting per segment
- [ ] Compression trigger logic
- [ ] LLM-based summarization for assistant messages
- [ ] Gentler summarization for user messages
- [ ] Preserve code blocks and quotes

### Phase 3: Repetition Detection
- [ ] Code block extraction and hashing
- [ ] Similarity detection (diff-based)
- [ ] Reference storage format
- [ ] Context reconstruction from references

### Phase 4: Hybrid Mode (Optional)
- [ ] Extract facts for semantic search (like current mode)
- [ ] Use semantic retrieval to supplement chronological context
- [ ] "What did we discuss about X?" queries

## Open Questions

1. **Absorption detection**: How do we know when LLM has "learned" something?
   - Track references in later responses?
   - Time-based heuristic (after N turns)?
   - Explicit user signal?

2. **Cross-session persistence**: How to handle proxy restarts?
   - Load full conversation from disk on startup?
   - Lazy loading with LRU cache?

3. **Multiple conversations**: Support multiple long conversations?
   - Use `memory_id` from request to switch?
   - Separate storage per conversation?

4. **Compression model**: Same model as chat, or smaller/faster?
   - Latency impact of compression
   - Quality vs speed tradeoff

## Comparison

| Aspect | Current `memory proxy` | Long Conversation Mode |
|--------|------------------------|------------------------|
| Context building | Semantic retrieval | Chronological + compressed |
| Compression | Symmetric | Asymmetric (user > LLM) |
| Repetition | None | Diff-based dedup |
| Retrieval | Vector similarity | Sequential history |
| Use case | Many short conversations | Single long conversation |
| Token budget | Implicit | Explicit (100-200k) |
