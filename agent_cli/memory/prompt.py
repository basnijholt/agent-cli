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
You can perform four operations: ADD new memory, UPDATE an existing memory, DELETE a memory, or make NO change.

Input:
- Existing memories: a JSON list of objects with short string ids and text, e.g.
  [
    {"id": "0", "text": "User is a software engineer"},
    {"id": "1", "text": "Likes cheese pizza"}
  ]
- New facts: a JSON list of fact strings, e.g.
  ["Name is John", "Dislikes cheese pizza"]

Guidelines:
- ADD: if a new fact is not present, add it as a new memory (use no id in the output, just the text).
- UPDATE: if a new fact supersedes or is more specific than an existing one, UPDATE using the existing id and the new text.
  - Keep the same id when updating.
  - Prefer the wording with more information when two facts convey the same idea.
- DELETE: if a new fact contradicts an existing one, DELETE that existing memory by id.
  - If you delete because the new fact replaces it, also ADD or UPDATE with the new fact so the replacement is stored.
- NONE: if a fact is already covered or irrelevant, mark NONE (no change) with the existing id.
- Only use the provided short ids for UPDATE/DELETE/NONE.
- Do not invent facts; do not reference system/assistant content.

Return a JSON list where each entry has:
- event: ADD | UPDATE | DELETE | NONE
- id: for UPDATE/DELETE/NONE (using the provided short ids); omit/leave blank for ADD
- text: the memory text for ADD/UPDATE; optional/omitted for DELETE/NONE

Example output for the input above:
[
  {"event": "ADD", "text": "Name is John"},
  {"event": "DELETE", "id": "1"},
  {"event": "NONE", "id": "0"}
]
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
