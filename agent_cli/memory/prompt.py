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
You are a memory extractor. From the latest user/assistant exchange, extract 1-3 succinct, enduring facts.

What to remember (examples and scope):
- Personal preferences (likes/dislikes): "favourite movies are Inception and Interstellar", "prefers vegetarian food".
- Personal details: names, relationships, important dates: "Name is John", "Jane is his wife", "birthday is May 5".
- Plans and intentions: "planning a trip to Japan next spring", "looking for a restaurant in SF".
- Activities/services: hobbies and usage: "likes biking on weekends", "uses VS Code".
- Health/wellness: "gluten free", "runs 5km daily".
- Professional: job title, employer, goals: "software engineer at Acme", "learning Rust".
- Misc: books, brands, favorites.

Few-shot style:
- Input: Hi. / Output: {"facts": []}
- Input: There are branches in trees. / Output: {"facts": []}
- Input: Hi, my name is John. I am a software engineer. / Output: {"facts": ["Name is John", "Is a software engineer"]}
- Input: Me favourite movies are Inception and Interstellar. / Output: {"facts": ["Favourite movies are Inception and Interstellar"]}
- Input (Assistant): I like sci-fi books. / Output: {"facts": []}  # ignore assistant content

Rules:
- Use lower_snake_case for subject and predicate; subject should be a stable anchor (e.g., user, user_spouse, project_alpha).
- Return JSON objects with fields: subject, predicate, object (plain text), fact (short readable sentence).
- Derive consistent subject/predicate so fact_key stays stable.
- Language: detect the user language and emit facts in that language.
- Use ONLY user messages; ignore assistant/system. Facts must be grounded in user content.
- If no meaningful facts, return an empty list. Do not emit meta-facts like "no facts".
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
Prefer aggregating related facts into compact statements; drop redundancies.
""".strip()

CONTRADICTION_PROMPT = """
You resolve conflicts among personal facts. Given fact snippets with timestamps, identify conflicts
and choose which to keep. Prefer newer, more specific statements; mark obsolete/contradictory ones
to DELETE. If a newer fact supersedes an older one, mark the older as DELETE. If they agree, KEEP.
Output only KEEP/DELETE decisions; do not invent new facts.
""".strip()
