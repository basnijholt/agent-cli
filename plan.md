# Memory Server Plan (Self-Hosted, Minimal Deps)

## Goals
- Long-term conversational memory with automatic extraction and retrieval.
- No hosted dependencies; reuse existing OpenAI-compatible LLM endpoints.
- Minimal new deps (reuse Chroma, httpx, pydantic, numpy already present).
- Preserve simple, OpenAI-compatible `/v1/chat/completions` surface.

## High-Level Architecture
- **Memory store**: Chroma collection keyed by `conversation_id`.
  - Documents: atomic memory entries (salient snippets or turn summaries).
  - Metadata: `conversation_id`, `role`, `created_at`, `summary_version`, `salience`, `tokens`.
  - Embeddings: reuse existing `--embedding-model` and base URL.
- **Short-term buffer**: recent raw turns kept in process memory; flushed to store after summarization.
- **Summaries**: rolling summaries per conversation stored as separate documents with a `summary` flag.
- **API**: `/v1/chat/completions` proxy; optional `memory_id` and `memory_top_k`.

## Retrieval & Augmentation Pipeline
1) Identify user message (latest user turn).
2) Retrieve:
   - semantic top-k from Chroma for `conversation_id`.
   - mix in most recent N raw turns (buffer) for recency.
3) Craft augmented prompt:
   - include recent turns (truncated).
   - include retrieved memory snippets (most salient first).
   - include latest summary block (if available).
4) Forward to backend LLM, stream as usual.

## Post-Completion Memory Update
- Append new user/assistant turns to short-term buffer.
- **Salience extraction**: ask the backend LLM to extract 1–3 salient facts from the new exchange (few-shot prompt, deterministic temperature).
- **Summarization**: when buffer tokens exceed threshold or every N turns:
  - Generate an updated rolling summary conditioned on prior summary + new salient facts.
  - Store/replace summary document (same `summary_version` metadata).
- **Upsert**: write salient facts as standalone memory entries with embeddings; evict or decay old low-salience entries by score/age.

## Memory Management / Replacement
- Keep per-conversation budget: `max_entries` (e.g., 500) and `max_age_days`.
- Eviction policy: drop lowest `salience` first; second key = oldest `created_at`.
- Decay salience over time (simple multiplicative decay on read/write).
- Optional `truncate` endpoint to wipe a conversation’s memory.

## Data Model (Chroma metadata)
- `conversation_id: str`
- `role: str` (user/assistant/system/summary)
- `created_at: iso8601`
- `salience: float`
- `summary_version: int` (for summary docs)
- `tokens: int` (estimated token count)

## Configuration / Flags
- `--memory-path` (Chroma persistence)
- `--embedding-model`, `--openai-base-url`, `--openai-api-key`
- `--memory-top-k` default (retrieval depth)
- `--max-memory-entries`, `--max-age-days`, `--salience-threshold`
- `--summary-trigger-tokens`, `--summary-max-length`

## Testing Strategy
- Unit: salience/summarization prompts produce expected shapes; eviction logic; metadata shaping.
- Integration: start app with temp Chroma, send chat turns, assert memory entries grow, retrieval includes summaries, eviction runs.
- Regression: ensure `rag-server` behavior unchanged; shared embedding config works.

## Implementation Milestones
1) **Scaffold**: new memory module with store, models, API; keep current OpenAI proxy flow.
2) **Retrieval**: semantic + recency merge; prompt augmentation.
3) **Update path**: buffer + salience extraction prompt + summary update; upsert into Chroma.
4) **Eviction/aging**: background or per-request sweep with salience decay and budget enforcement.
5) **Config & docs**: CLI flags, README usage, install extras.
6) **Tests**: unit + small integration harness with temporary Chroma and mock backend LLM.
