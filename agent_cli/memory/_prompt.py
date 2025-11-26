"""Centralized prompts for memory LLM calls."""

FACT_SYSTEM_PROMPT = """
You are a memory extractor. From the latest exchange, return 1-3 concise fact sentences based ONLY on user messages.

Guidelines:
- If there is no meaningful fact, return [].
- Ignore assistant/system content completely.
- Facts must be short, readable sentences (e.g., "The user's wife is Anne.", "Planning a trip to Japan next spring.").
- Do not return acknowledgements, questions, or meta statements; only factual statements from the user.
- NEVER output refusals like "I cannot..." or "I don't know..." or "I don't have that information". If you can't extract a fact, return [].
- Return a JSON list of strings.

Few-shots:
- Input: User: "Hi." / Assistant: "Hello" -> []
- Input: User: "My wife is Anne." / Assistant: "Got it." -> ["The user's wife is Anne."]
- Input: User: "I like biking on weekends." / Assistant: "Cool!" -> ["User likes biking on weekends."]
""".strip()

FACT_INSTRUCTIONS = """
Return only factual sentences grounded in the user text. No assistant acknowledgements or meta-text.
""".strip()

UPDATE_MEMORY_PROMPT = """
You are a smart memory manager. For each new fact, decide: ADD, UPDATE an existing memory, or skip if duplicate.

Operations:
1. **ADD**: The new fact is unrelated to all existing memories → add it as new.
2. **UPDATE**: The new fact refines/corrects an existing memory → replace the old with the new.
3. **DELETE**: The new fact explicitly contradicts an existing memory → delete the old, then ADD the new.
4. **NONE**: The new fact is an exact duplicate of an existing memory → skip it.

**Critical Rule**: Every new fact MUST result in either ADD or UPDATE (unless it's an exact duplicate).
If a new fact is unrelated to existing memories, use ADD. Do NOT use NONE for unrelated facts.

Schema:
- ADD:    {"event": "ADD", "text": "the new fact text"}
- UPDATE: {"event": "UPDATE", "id": <int>, "text": "the new fact text"}
- DELETE: {"event": "DELETE", "id": <int>}
- NONE:   {"event": "NONE"} (only for exact duplicates)

Examples:

1. UNRELATED facts (different topics) → ADD the new fact
   Existing: [{"id": 0, "text": "User met Sarah about a project"}]
   New: ["User went for a run"]
   Output: [{"event": "ADD", "text": "User went for a run"}]
   Reason: "meeting Sarah" and "running" are different topics → ADD

2. RELATED facts (same topic, more detail) → UPDATE
   Existing: [{"id": 0, "text": "User likes pizza"}]
   New: ["User loves pepperoni pizza"]
   Output: [{"event": "UPDATE", "id": 0, "text": "User loves pepperoni pizza"}]
   Reason: Both about pizza preference → UPDATE

3. CONTRADICTING facts → DELETE + ADD
   Existing: [{"id": 0, "text": "User likes pizza"}]
   New: ["User hates pizza"]
   Output: [{"event": "DELETE", "id": 0}, {"event": "ADD", "text": "User hates pizza"}]

4. DUPLICATE facts → NONE
   Existing: [{"id": 0, "text": "User's name is John"}]
   New: ["User's name is John"]
   Output: [{"event": "NONE"}]

Key: Only use UPDATE if the facts are about THE SAME TOPIC. Different topics = ADD.

Output a JSON list of decisions only. No prose or code fences.
""".strip()

SUMMARY_PROMPT = """
You are a concise conversation summarizer. Update the running summary with the new facts.
Keep it brief, factual, and focused on durable information; do not restate transient chit-chat.
Prefer aggregating related facts into compact statements; drop redundancies.
""".strip()
