"""Centralized prompts for memory LLM calls."""

CONSOLIDATION_PROMPT = """
You are reconciling overlapping facts for a personal memory store.
Given a small list of fact snippets with timestamps, mark each as KEEP, UPDATE, or DELETE
so only the most accurate, non-contradictory set remains. Prefer newer timestamps when content
conflicts; if two are equivalent, keep one. UPDATE when a newer statement supersedes an older one;
DELETE stale/contradictory duplicates. Output only the decision list—do not invent new facts.
""".strip()

QUERY_REWRITE_PROMPT = """
Rewrite the user request into up to three high-recall search queries.
Include explicit entities, aliases, paraphrases, and disambiguated forms.
Return a JSON list of plain strings. No explanations.
""".strip()

FACT_SYSTEM_PROMPT = """
You are a memory extractor. From the latest user/assistant exchange, extract 1-3 succinct, enduring facts.
Return JSON objects with fields:
- subject (lower_snake_case anchor, e.g., 'user', 'user_spouse', 'project_alpha')
- predicate (lower_snake_case relation, e.g., 'name', 'wife', 'location', 'job_title')
- object (plain text value)
- fact (short readable sentence).
The system derives fact_key from subject+predicate—keep them consistent.
Never return meta-facts like 'no information to extract'. If there are no meaningful facts, return an empty list.
""".strip()

FACT_INSTRUCTIONS = """
Keep facts atomic, enduring, and person-centered when possible.
Prefer explicit subjects over pronouns. Use lower_snake_case for subject/predicate
(e.g., 'user|wife', 'bas_nijholt|employer', 'bike|type').
Avoid formatting; return only JSON.
""".strip()

SUMMARY_PROMPT = """
You are a concise conversation summarizer. Update the running summary with the new facts.
Keep it brief, factual, and focused on durable information; do not restate transient chit-chat.
""".strip()

CONTRADICTION_PROMPT = """
You resolve conflicts among personal facts. Given fact snippets with timestamps, identify conflicts
and choose which to keep. Prefer newer, more specific statements; mark obsolete/contradictory ones
to DELETE. If a newer fact supersedes an older one, mark the older as DELETE. If they agree, KEEP.
Output only KEEP/DELETE decisions; do not invent new facts.
""".strip()
