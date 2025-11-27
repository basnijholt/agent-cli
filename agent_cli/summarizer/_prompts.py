"""Prompt templates for adaptive summarization.

These prompts are designed to work with various LLM sizes (8B-20B parameters)
and are optimized for structured, factual output.
"""

# BRIEF level - Single sentence summary for short content (100-500 tokens)
BRIEF_SUMMARY_PROMPT = """Summarize the following in ONE sentence (maximum 20 words).
Focus on the single most important point or takeaway.

Content:
{content}

One-sentence summary:""".strip()

# MAP_REDUCE level - Paragraph summary for content-type aware summarization
STANDARD_SUMMARY_PROMPT = """Summarize the following content concisely in a short paragraph.

Focus on:
- Key facts, decisions, and outcomes
- Important context that should be remembered
- Skip transient details, greetings, and chitchat

{prior_context}

Content to summarize:
{content}

Summary (maximum {max_words} words):""".strip()

# CHUNK - Used in map phase of map-reduce summarization
CHUNK_SUMMARY_PROMPT = """Summarize this section of a longer document.
Capture the main points while preserving important details.

Section {chunk_index} of {total_chunks}:
{content}

Summary of this section (maximum {max_words} words):""".strip()

# META - Combine multiple summaries in reduce phase
META_SUMMARY_PROMPT = """Synthesize these summaries into a single coherent overview.
Identify common themes and key points across all sections.
Eliminate redundancy while preserving unique insights.

Summaries to combine:
{summaries}

Combined summary (maximum {max_words} words):""".strip()

# For conversation-specific summarization
CONVERSATION_SUMMARY_PROMPT = """Summarize this conversation from the AI assistant's perspective.
Focus on:
- What the user wanted or asked about
- Key information the user shared about themselves
- Decisions made or conclusions reached
- Any commitments or follow-ups mentioned

{prior_context}

Conversation:
{content}

Summary (maximum {max_words} words):""".strip()

# For journal/personal content
JOURNAL_SUMMARY_PROMPT = """Summarize this personal entry or reflection.
Preserve:
- Key events and experiences mentioned
- Emotions and insights expressed
- Goals, plans, or intentions stated
- People, places, or things that are important

{prior_context}

Entry:
{content}

Summary (maximum {max_words} words):""".strip()

# For technical/document content
DOCUMENT_SUMMARY_PROMPT = """Summarize this technical content or documentation.
Focus on:
- Main concepts and their relationships
- Key procedures or processes described
- Important specifications or requirements
- Conclusions or recommendations

{prior_context}

Document:
{content}

Summary (maximum {max_words} words):""".strip()


def get_prompt_for_content_type(content_type: str) -> str:
    """Get the appropriate prompt template for a content type.

    Args:
        content_type: One of "general", "conversation", "journal", "document".

    Returns:
        The prompt template string.

    """
    prompts = {
        "general": STANDARD_SUMMARY_PROMPT,
        "conversation": CONVERSATION_SUMMARY_PROMPT,
        "journal": JOURNAL_SUMMARY_PROMPT,
        "document": DOCUMENT_SUMMARY_PROMPT,
    }
    return prompts.get(content_type, STANDARD_SUMMARY_PROMPT)


def format_prior_context(prior_summary: str | None) -> str:
    """Format prior summary context for inclusion in prompts."""
    if prior_summary:
        return f"Prior context (for continuity):\n{prior_summary}\n"
    return ""


def format_summaries_for_meta(summaries: list[str]) -> str:
    """Format a list of summaries for the meta-summary prompt."""
    formatted = []
    for i, summary in enumerate(summaries, 1):
        formatted.append(f"[Section {i}]\n{summary}")
    return "\n\n".join(formatted)
