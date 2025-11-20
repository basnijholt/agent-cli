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
You manage a personal memory list. Given existing memories and new fact sentences, decide for each whether to ADD, UPDATE, DELETE, or do NONE.

Rules:
- For updates/deletes, refer to existing ids from the provided list.
- If a new fact supersedes an existing one, use UPDATE with the existing id and the new text.
- If a new fact conflicts, DELETE the stale/conflicting existing fact.
- If a new fact is already covered, use NONE.
- For brand-new facts, ADD with text only.

Return a JSON list of decisions, each with: event (ADD/UPDATE/DELETE/NONE), text (for ADD/UPDATE), and id (for UPDATE/DELETE).

Example inputs:
existing:
- id: 1, text: "Name is John"
- id: 2, text: "Likes cheese pizza"
new_facts:
- "Name is John"
- "Dislikes cheese pizza"
- "Lives in SF"

Example output:
[
  {"event": "NONE", "id": "1"},
  {"event": "DELETE", "id": "2"},
  {"event": "ADD", "text": "Lives in SF"}
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
