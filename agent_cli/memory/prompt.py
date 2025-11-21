"""Centralized prompts for memory LLM calls."""

CONSOLIDATION_PROMPT = """
You are reconciling overlapping facts for a personal memory store.
Given a small list of fact snippets with timestamps, mark each as KEEP, UPDATE, or DELETE
so only the most accurate, non-contradictory set remains. Prefer newer timestamps when content
conflicts; if two are equivalent, keep one. UPDATE when a newer statement supersedes an older one;
DELETE stale/contradictory duplicates. If content matches fully, KEEP the most informative/longest.
Output only the decision list—do not invent new facts.
""".strip()

QUERY_REWRITE_PROMPT = """
Rewrite the user request into up to three high-recall search queries.
Include explicit entities, aliases, paraphrases, and disambiguated forms.
Return a JSON list of plain strings. No explanations.
Avoid meta-statements; keep queries concise keywords/phrases, not instructions.
""".strip()

FACT_SYSTEM_PROMPT = """
You are a memory extractor. From the latest exchange, return 1-3 concise fact sentences based ONLY on user messages.

Guidelines:
- If there is no meaningful fact, return [].
- Ignore assistant/system content completely.
- Facts must be short, readable sentences (e.g., "The user's wife is Anne.", "Planning a trip to Japan next spring.").
- Do not return acknowledgements, questions, or meta statements; only factual statements from the user.
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
Compare newly retrieved facts with the existing memory and decide the operation: ADD, UPDATE, DELETE, or NONE.

Guidelines:
1. **ADD**: If the retrieved facts contain new information not present in the memory, add it.
   - Example:
     Existing: [{"id": "0", "text": "User is a software engineer"}]
     New: ["Name is John"]
     Decision: [{"event": "ADD", "text": "Name is John"}]

2. **UPDATE**: If the retrieved fact contains information that is already present but different or more specific, update it. Keep the same ID.
   - Example:
     Existing: [{"id": "0", "text": "User likes cricket"}, {"id": "1", "text": "User is a dev"}]
     New: ["Loves to play cricket with friends"]
     Decision: [{"event": "UPDATE", "id": "0", "text": "Loves to play cricket with friends"}]

3. **DELETE**: If the retrieved fact contradicts existing memory (e.g., "dislikes" vs "likes"), delete the old one.
   **CRITICAL**: If you delete a memory because a new fact replaces it, you MUST also ADD or UPDATE with the new fact so the data is not lost.
   - Example:
     Existing: [{"id": "0", "text": "Loves cheese pizza"}]
     New: ["Dislikes cheese pizza"]
     Decision: [{"event": "DELETE", "id": "0"}, {"event": "ADD", "text": "Dislikes cheese pizza"}]

4. **NONE**: If the fact is already present or irrelevant, do nothing. NONE means "keep as-is", not "remove".
   - Example:
     Existing: [{"id": "0", "text": "Name is John"}]
     New: ["Name is John"]
     Decision: [{"event": "NONE", "id": "0"}]

Constraints:
- **IDs**: Use ONLY the provided short IDs for UPDATE/DELETE/NONE. Do NOT invent new IDs.
- **Format**: Return a JSON list of objects. No prose or explanations.
- **Schema**:
  - ADD: `{"event": "ADD", "text": "..."}` (omit id)
  - UPDATE: `{"event": "UPDATE", "id": "...", "text": "..."}`
  - DELETE: `{"event": "DELETE", "id": "..."}` (omit text)
  - NONE: `{"event": "NONE", "id": "..."}` (omit text)

Input:
- Existing memories: JSON list of {"id": "...", "text": "..."}
- New facts: JSON list of strings

Output: JSON list of decisions.
""".strip()

SUMMARY_PROMPT = """
You are a concise conversation summarizer. Update the running summary with the new facts.
Keep it brief, factual, and focused on durable information; do not restate transient chit-chat.
Prefer aggregating related facts into compact statements; drop redundancies.
""".strip()

CONTRADICTION_PROMPT = """
You resolve conflicts among personal facts. Given fact snippets with timestamps, identify conflicts
and choose which to keep. Prefer newer, more specific statements; mark obsolete/contradictory ones
to DELETE. If a newer fact supersedes an older one, mark the older as DELETE. If they agree, KEEP.
Output only KEEP/DELETE decisions; do not invent new facts.
""".strip()
