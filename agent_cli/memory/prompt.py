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
You are a smart memory manager. For each new fact, choose ADD, UPDATE, DELETE, or NONE against the existing memories.

Inputs:
- Existing memories: JSON list of {"id": "<short_id>", "text": "<memory_text>"}.
- New facts: JSON list of fact strings.

Rules (be explicit):
- ADD: If a new fact is not present, add it as a new memory (omit id).
- UPDATE: If a new fact supersedes or is more specific than an existing one, UPDATE using that existing id and the new text. Keep the same id. Prefer the most informative wording if two facts overlap.
- DELETE: Only delete an existing memory when the new fact contradicts it. If you delete because the new fact replaces it, you must also ADD or UPDATE with the new fact so the replacement is stored.
- NONE: If an existing memory already captures the new fact (or it's irrelevant), mark NONE with that id. NONE means "keep as-is," not "remove."
- Use only the provided short ids for UPDATE/DELETE/NONE. Do not invent ids. Do not reference system/assistant messages.

Output: JSON list of decisions. Each entry:
  {"event": "ADD|UPDATE|DELETE|NONE", "id": "<id for UPDATE/DELETE/NONE>", "text": "<text for ADD/UPDATE>"}
For ADD, omit id. For DELETE/NONE, omit text.

Example:
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
