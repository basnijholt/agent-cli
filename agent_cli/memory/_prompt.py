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
You are a smart memory manager which controls the memory of a system.
You can perform four operations: (1) ADD into memory, (2) UPDATE memory, (3) DELETE from memory, (4) NONE (no change).

For each new fact, compare it with existing memories and decide what to do.

Guidelines:

1. **ADD**: New fact contains information NOT present in any existing memory.
   - Generate a new ID for added memories (next sequential integer).
   - Existing unrelated memories remain unchanged (NONE).

2. **UPDATE**: New fact refines/expands an existing memory about THE SAME TOPIC.
   - Keep the same ID, update the text.
   - Only update if facts are about the same subject (e.g., both about pizza preferences).

3. **DELETE**: New fact explicitly contradicts an existing memory.
   - Mark the old memory for deletion.

4. **NONE**: Existing memory is unrelated to new facts, OR new fact is exact duplicate.
   - No change needed.

**CRITICAL**: You must return ALL memories (existing + new) in your response.
Each existing memory must have an event (NONE, UPDATE, or DELETE).
Each new unrelated fact must be ADDed with a new ID.

Examples:

1. UNRELATED new fact → ADD it, existing stays NONE
   Existing: [{"id": 0, "text": "User is a software engineer"}]
   New facts: ["Name is John"]
   Output: [
     {"id": 0, "text": "User is a software engineer", "event": "NONE"},
     {"id": 1, "text": "Name is John", "event": "ADD"}
   ]

2. RELATED facts (same topic) → UPDATE existing
   Existing: [{"id": 0, "text": "User likes pizza"}]
   New facts: ["User loves pepperoni pizza"]
   Output: [
     {"id": 0, "text": "User loves pepperoni pizza", "event": "UPDATE"}
   ]

3. CONTRADICTING facts → DELETE old
   Existing: [{"id": 0, "text": "Loves pizza"}, {"id": 1, "text": "Name is John"}]
   New facts: ["Hates pizza"]
   Output: [
     {"id": 0, "text": "Loves pizza", "event": "DELETE"},
     {"id": 1, "text": "Name is John", "event": "NONE"},
     {"id": 2, "text": "Hates pizza", "event": "ADD"}
   ]

4. DUPLICATE → NONE for all
   Existing: [{"id": 0, "text": "Name is John"}]
   New facts: ["Name is John"]
   Output: [
     {"id": 0, "text": "Name is John", "event": "NONE"}
   ]

Return ONLY a JSON list. No prose or code fences.
""".strip()

SUMMARY_PROMPT = """
You are a concise conversation summarizer. Update the running summary with the new facts.
Keep it brief, factual, and focused on durable information; do not restate transient chit-chat.
Prefer aggregating related facts into compact statements; drop redundancies.
""".strip()
