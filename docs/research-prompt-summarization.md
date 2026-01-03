# Deep Research Prompt: Adaptive Memory Summarization for Personal Knowledge Systems

## Background & Context

We are building **agent-cli**, an open-source memory layer for AI agents and personal knowledge systems. The goal is to create a system that can:

1. **Remember who you are** - Extract and maintain facts about the user over time
2. **Learn and improve** - Facts should have confidence/strength that increases with repeated observations and decays with contradictions
3. **Scale gracefully** - Handle inputs ranging from 5 lines to 100,000+ tokens (entire books, long conversations, document collections)
4. **Work with local LLMs** - Must function with models running on consumer hardware (8B-20B parameters, 8K-32K context windows)

### Current Architecture

We have two related systems:

**agent-cli MemoryClient** (~700 LOC):
- ChromaDB vector store for embeddings
- PydanticAI agents for fact extraction
- ADD/UPDATE/DELETE/NONE reconciliation (LLM decides how new facts relate to existing ones)
- Rolling conversation summaries
- MMR reranking with ONNX cross-encoder

**aijournal** (~21K LOC):
- Typed "ClaimAtoms" with: type (preference|goal|habit|value|trait|skill), strength (0.0-1.0), provenance, observation_count
- 8-stage pipeline: persist → normalize → summarize → facts → profile → index → persona → pack
- Hierarchical context packs (L1-L4) with token budgets
- Feedback system: [claim:id] markers + thumbs up/down → strength adjustment

### The Core Problem

Current summarization is **static and one-size-fits-all**:

```python
# Current approach - same treatment for all inputs
summary = llm.summarize(content, max_tokens=256)
```

This fails because:
- A 5-line journal entry doesn't need a 256-token summary
- A 50,000-token conversation loses critical nuance when compressed to 256 tokens
- A technical document has different summarization needs than a personal reflection
- Long-running conversations need continuous summarization, not batch processing

### What We Want

A **multi-level adaptive summarization system** that:

1. **Scales summary depth with input complexity** - More content = richer, hierarchical summary structure
2. **Preserves retrievable detail** - Don't flatten everything; maintain a tree of summaries at different granularities
3. **Handles streaming/continuous input** - For ongoing conversations, not just static documents
4. **Extracts both facts AND narrative context** - Facts are atomic truths; summaries provide coherent context
5. **Works within context window limits** - Must handle inputs longer than any LLM's context window
6. **Supports different content types** - Journal entries, LLM conversations, technical docs, meeting notes, books

---

## Research Questions

Please investigate the following questions with **specific citations to papers, production systems, or documented implementations**. For each answer, provide:
- The technique/approach name
- Source (paper, documentation, codebase)
- How it works (concrete algorithm/pseudocode if possible)
- Tradeoffs (latency, token cost, quality, complexity)
- Evidence of effectiveness (benchmarks, user studies, production metrics)

### 1. Hierarchical Summarization Architectures

**Q1.1**: What are the proven approaches for hierarchical/multi-level summarization of long documents?
- How do systems like NexusSum, BOOOOKSCORE, and HMT (Hierarchical Memory Transformer) structure their summary trees?
- What chunk sizes and overlap strategies work best at each level?
- How do you decide the depth of the hierarchy for a given input?

**Q1.2**: How should summary length scale with input length?
- Is there research on optimal compression ratios at different scales?
- What is the "information density" tradeoff - how much can you compress before critical information loss?
- Are there adaptive algorithms that determine summary length based on content complexity (not just token count)?

**Q1.3**: How do you maintain coherence across hierarchical summary levels?
- When summarizing summaries, how do you avoid "semantic drift" where meaning shifts?
- What techniques exist for ensuring the top-level summary accurately represents the leaf-level content?

### 2. Continuous/Streaming Summarization

**Q2.1**: How do production systems handle ongoing conversations that exceed context windows?
- How does MemGPT/Letta implement its eviction and recursive summarization?
- How does Claude Code's "auto-compact" work when context exceeds 95%?
- What does Mem0's "rolling summary" architecture look like in detail?

**Q2.2**: What is the state-of-the-art for "infinite context" via summarization?
- How does Cognitive Workspace achieve 58.6% memory reuse?
- What are the key techniques from the "Functional Infinite Context" paper?
- How do systems decide WHAT to evict vs. keep in working memory?

**Q2.3**: How do you handle the "recency vs. importance" tradeoff?
- Recent messages are often more relevant, but older messages may contain critical context
- What weighting schemes or heuristics exist for balancing these?
- How do systems like Letta's "sleep-time agents" handle background memory consolidation?

### 3. Fact Extraction vs. Summarization

**Q3.1**: What is the relationship between extractive summarization, abstractive summarization, and fact/claim extraction?
- When should you extract discrete facts vs. generate a narrative summary?
- How do systems like Mem0 decide what becomes a "memory" vs. what stays in the summary?
- What is the optimal interplay between a knowledge graph and narrative summaries?

**Q3.2**: How do graph-based memory systems (Mem0ᵍ, knowledge graphs) complement or replace traditional summarization?
- When is a graph representation better than a text summary?
- How do you query a hybrid system (graph + summaries + raw embeddings)?
- What are the token costs and latency implications of graph extraction?

**Q3.3**: How should facts/claims be typed and weighted?
- What taxonomies exist for classifying personal knowledge (preferences, goals, habits, traits)?
- How do systems implement confidence/strength scoring for facts?
- What decay functions or reinforcement mechanisms are used in production?

### 4. Content-Type Adaptive Strategies

**Q4.1**: Should summarization strategies differ by content type?
- How should you summarize a personal journal entry vs. a technical document vs. an LLM conversation?
- Are there content-type detection mechanisms that inform summarization strategy?
- What does "style-preserving" summarization look like for personal content?

**Q4.2**: How do you handle multi-modal or structured content?
- Code blocks, tables, lists within documents
- Conversations with tool calls and structured outputs
- Documents with hierarchical structure (headers, sections)

### 5. Quality and Evaluation

**Q5.1**: How do you evaluate summarization quality for personal knowledge systems?
- What metrics beyond ROUGE/BERTScore are relevant?
- How do you measure "information preservation" across compression levels?
- What user-centric metrics exist (e.g., can the user reconstruct intent from the summary)?

**Q5.2**: What are the failure modes of hierarchical summarization?
- What causes "hallucination" or "drift" in multi-level summarization?
- How do you detect and recover from summarization errors?
- What quality gates should exist between summarization levels?

### 6. Production Implementation

**Q6.1**: What are the concrete architectures of production memory systems?
- Mem0's full pipeline (extraction → update → retrieval)
- Letta/MemGPT's memory hierarchy (core → conversational → archival → recall)
- Zep's memory layer architecture
- LangMem or similar open-source implementations

**Q6.2**: What are the latency and cost characteristics?
- How do systems achieve sub-second memory operations?
- What is the token cost per memory operation in production systems?
- What caching strategies are used?

**Q6.3**: How do systems handle context window limitations with local LLMs?
- Strategies for 8K-32K context models
- Chunking and batching approaches that work with smaller models
- Quality degradation curves as model size decreases

### 7. Specific Technical Questions

**Q7.1**: What is the optimal chunk size for summarization?
- Does this vary by model size, content type, or summarization level?
- What overlap (if any) should exist between chunks?
- How do you handle semantic boundaries (paragraphs, sections) vs. fixed token counts?

**Q7.2**: How should summaries be stored and indexed?
- Should summaries be embedded alongside or separately from source content?
- How do you retrieve across multiple summary levels efficiently?
- What metadata should accompany summaries?

**Q7.3**: What prompt engineering techniques improve summarization quality?
- Chain-of-thought for summarization
- Few-shot examples
- Structured output formats (JSON, XML) for summaries

---

## Constraints & Requirements

Any proposed solution must:

1. **Work with local LLMs** (Llama 3.1 8B, Qwen 20B, Mistral 7B) with 8K-32K context
2. **Be implementable in Python** with PydanticAI, ChromaDB, and standard tooling
3. **Have sub-2-second latency** for typical operations (adding a memory, searching)
4. **Be storage-efficient** - we're storing on local disk, not cloud
5. **Be backed by evidence** - prefer techniques with published benchmarks or production deployments

---

## Desired Output Format

For each research question, provide:

```markdown
### [Question ID]: [Question Title]

**Answer**: [Concise answer]

**Technique(s)**:
- Name: [Technique name]
- Source: [Paper/docs/codebase URL]
- How it works: [Algorithm description or pseudocode]
- Evidence: [Benchmarks, metrics, or production data]
- Tradeoffs: [Pros and cons]

**Recommended Approach for agent-cli**:
[Specific recommendation with justification]

**Implementation Sketch**:
```python
# Pseudocode or concrete implementation
```
```

---

## Success Criteria

The research is successful if it enables us to:

1. Design a `SummaryLevel` enum and `AdaptiveSummarizer` class with clear, evidence-based design choices
2. Implement hierarchical summarization that scales from 100 to 100,000+ tokens
3. Integrate with our existing fact extraction and reconciliation pipeline
4. Maintain quality with local LLMs (not just GPT-4/Claude)
5. Achieve Mem0-like efficiency (90%+ token savings vs. full context)

---

## Related Work to Start With

These are known relevant sources - please expand beyond these:

- [Mem0 Paper (arXiv:2504.19413)](https://arxiv.org/abs/2504.19413) - April 2025
- [MemGPT Paper (arXiv:2310.08560)](https://arxiv.org/abs/2310.08560) - October 2023
- [NexusSum (arXiv:2505.24575)](https://arxiv.org/abs/2505.24575) - May 2025
- [HMT: Hierarchical Memory Transformer (NAACL 2025)](https://aclanthology.org/2025.naacl-long.410.pdf)
- [BOOOOKSCORE (ICLR 2024)](https://openreview.net/pdf?id=7Ttk3RzDeu)
- [Cognitive Workspace (arXiv:2508.13171)](https://arxiv.org/html/2508.13171v1)
- [Letta Documentation](https://docs.letta.com/)
- [Mem0 Documentation](https://docs.mem0.ai/)
- [LangChain Summarization](https://python.langchain.com/docs/tutorials/summarization/)
- [Context Engineering for Agents (Lance Martin)](https://rlancemartin.github.io/2025/06/23/context_engineering/)
