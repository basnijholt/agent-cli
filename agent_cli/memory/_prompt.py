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

UPDATE_MEMORY_PROMPT = """You are a smart memory manager which controls the memory of a system.
You can perform four operations: (1) ADD into the memory, (2) UPDATE the memory, (3) DELETE from the memory, and (4) NONE (no change).

Compare new facts with existing memory. For each new fact, decide whether to:
- ADD: Add it to the memory as a new element (new information not present in any existing memory)
- UPDATE: Update an existing memory element (only if facts are about THE SAME TOPIC, e.g., both about pizza preferences)
- DELETE: Delete an existing memory element (if new fact explicitly contradicts it)
- NONE: Make no change (if fact is already present, a duplicate, or the existing memory is unrelated to new facts)

**Guidelines:**

1. **ADD**: If the new fact contains new information not present in any existing memory, add it with a new ID.
   - Existing unrelated memories should have event "NONE".
- **Example**:
    - Current memory: [{"id": 0, "text": "User is a software engineer"}]
    - New facts: ["Name is John"]
    - Output: [
        {"id": 0, "text": "User is a software engineer", "event": "NONE"},
        {"id": 1, "text": "Name is John", "event": "ADD"}
      ]

2. **UPDATE**: Only if the new fact refines/expands an existing memory about THE SAME TOPIC.
   - Keep the same ID, update the text.
   - Example: "User likes pizza" + "User loves pepperoni pizza" → UPDATE (same topic: pizza)
   - Example: "Met Sarah today" + "Went running" → NOT same topic, do NOT update!
- **Example**:
    - Current memory: [{"id": 0, "text": "User likes pizza"}]
    - New facts: ["User loves pepperoni pizza"]
    - Output: [{"id": 0, "text": "User loves pepperoni pizza", "event": "UPDATE"}]

3. **DELETE**: If the new fact explicitly contradicts an existing memory.
- **Example**:
    - Current memory: [{"id": 0, "text": "Loves pizza"}, {"id": 1, "text": "Name is John"}]
    - New facts: ["Hates pizza"]
    - Output: [
        {"id": 0, "text": "Loves pizza", "event": "DELETE"},
        {"id": 1, "text": "Name is John", "event": "NONE"},
        {"id": 2, "text": "Hates pizza", "event": "ADD"}
      ]

4. **NONE**: If the new fact is already present or existing memory is unrelated to new facts.
- **Example**:
    - Current memory: [{"id": 0, "text": "Name is John"}]
    - New facts: ["Name is John"]
    - Output: [{"id": 0, "text": "Name is John", "event": "NONE"}]

5. **IMPORTANT - Unrelated topics example**:
    - Current memory: [{"id": 0, "text": "Met Sarah to discuss quantum computing"}]
    - New facts: ["Went for a 5km run"]
    - These are COMPLETELY DIFFERENT topics (meeting vs running). Do NOT use UPDATE!
    - Output: [
        {"id": 0, "text": "Met Sarah to discuss quantum computing", "event": "NONE"},
        {"id": 1, "text": "Went for a 5km run", "event": "ADD"}
      ]

**CRITICAL RULES:**
- You MUST return ALL memories (existing + new) in your response.
- Each existing memory MUST have an event (NONE, UPDATE, or DELETE).
- Each genuinely NEW fact (not related to any existing memory) MUST be ADDed with a new ID.
- Do NOT use UPDATE for unrelated topics! "Met Sarah" and "Went running" are DIFFERENT topics → use NONE for existing + ADD for new.

Return ONLY a JSON list. No prose or code fences.""".strip()

SUMMARY_PROMPT = """
You are a concise conversation summarizer. Update the running summary with the new facts.
Keep it brief, factual, and focused on durable information; do not restate transient chit-chat.
Prefer aggregating related facts into compact statements; drop redundancies.
""".strip()
