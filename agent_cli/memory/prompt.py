"""Centralized prompts for memory LLM calls."""

CONSOLIDATION_PROMPT = (
    "You are reconciling overlapping facts for a personal memory store. "
    "Given a small list of fact snippets with timestamps, mark each as KEEP or DELETE "
    "so that only the most accurate, non-contradictory set remains. "
    "Prefer newer timestamps when content conflicts. If two are equivalent, keep one. "
    "UPDATE may be used when a newer statement supersedes an older one; DELETE the stale one. "
    "Output a list of decisions; do not invent new facts."
)

QUERY_REWRITE_PROMPT = (
    "Rewrite the user request into up to a few search queries that maximize recall. "
    "Include explicit entities (names, aliases), paraphrases, and disambiguated forms. "
    "Return a JSON list of plain strings. Do not include explanations."
)

FACT_SYSTEM_PROMPT = (
    "You are a memory extractor. From the latest exchange, extract 1-3 succinct facts "
    "that are useful to remember for future turns. Return JSON objects with fields: "
    "- subject (lower_snake_case, stable anchor, e.g., 'user', 'user_spouse', 'project_alpha') "
    "- predicate (lower_snake_case relation, e.g., 'name', 'wife', 'location', 'job_title') "
    "- object (plain text value) "
    "- fact (a short readable sentence). "
    "The system will derive a fact_key from subject + predicate, so keep those consistent. "
    "Do not include prose outside JSON. If there are no facts, return an empty list. "
    "Never return meta-facts like 'no information to extract'."
)

FACT_INSTRUCTIONS = (
    "Keep facts atomic, enduring, and person-centered when possible. "
    "Prefer explicit subjects (names) over pronouns. Use lower_snake_case for subject and predicate. "
    "Examples: 'user|wife', 'bas_nijholt|employer', 'bike|type'. "
    "Avoid formatting; return only JSON."
)

SUMMARY_PROMPT = (
    "You are a concise conversation summarizer. Update the running summary with the new facts. "
    "Keep it brief and focused on enduring information."
)
