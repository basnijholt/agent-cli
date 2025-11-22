# Critical Review of Memory Architecture Refactor

**Commit:** `0f78a7b`
**Date:** November 22, 2025
**Subject:** `refactor(memory): simplify architecture by removing query rewriting, consolidation, and dual summaries`

## Executive Summary

This document reviews the recent architectural simplification of the memory system. The refactor removed three key components: **Query Rewriting**, **Read-Time Consolidation**, and **Dual Summaries**.

**Verdict:** The refactor was largely positive, removing unnecessary complexity and latency. However, **Query Rewriting** was removed prematurely and should be restored as an optional configuration to ensure high recall for semantic searches.

## Component Analysis

### 1. Query Rewriting (Verdict: ⚠️ Restore as Optional)

*   **Functionality:** Used an LLM to generate synonyms, entity aliases, and disambiguated forms of the user's query (e.g., mapping "my ride" to "Honda Civic") prior to vector retrieval.
*   **Critique:** Removing this significantly lowers recall. Vector databases often struggle with vocabulary mismatch (the "lexical gap"). While this step adds latency (one extra LLM call per turn), it is often necessary for a robust memory system where the user's query phrasing doesn't match the stored memory's phrasing.
*   **Recommendation:** **Restore this functionality.** It should be exposed as a configurable option (e.g., `enable_query_rewriting=True/False`), allowing users to trade latency for recall.

### 2. Read-Time Consolidation (Verdict: ✅ Keep Removed)

*   **Functionality:** Performed a synchronous LLM call *during retrieval* to deduplicate and conflict-check retrieved memories before passing them to the chat agent.
*   **Critique:** This was an anti-pattern. Conflict resolution and deduplication are "write-time" concerns. Performing this on the "read path" adds unacceptable latency to every user interaction and masks dirty data in the underlying store. The current `_reconcile_facts` (Write-Time) logic handles this correctly in the background.
*   **Recommendation:** **Do not revert.** Rely on background reconciliation to keep the database clean.

### 3. Dual Summaries (Verdict: ✅ Keep Removed)

*   **Functionality:** Maintained two separate rolling summaries (Short vs. Long) for every conversation.
*   **Critique:** This added significant complexity, token overhead, and storage costs with little proven benefit for a personal agent. A single, well-maintained summary is sufficient for providing context.
*   **Recommendation:** **Do not revert.**

## Action Items

1.  Restore `QUERY_REWRITE_PROMPT` to `agent_cli/memory/prompt.py`.
2.  Restore the `_rewrite_queries` function in `agent_cli/memory/engine.py`.
3.  Update `ChatRequest` and `MemoryClient` to accept an `enable_query_rewriting` flag.
4.  Update the retrieval pipeline to optionally use rewritten queries.
