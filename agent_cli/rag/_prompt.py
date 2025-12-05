"""Centralized prompts for RAG LLM calls."""

RAG_PROMPT_WITH_TOOLS = """
## Retrieved Documentation
The following was automatically retrieved based on the user's query:

<retrieved_documents>
{context}
</retrieved_documents>

## RAG Instructions
- Use the retrieved context ONLY if it's relevant to the question
- If the context is irrelevant, ignore it and answer based on your knowledge
- When using context, cite sources: [Source: filename]
- If snippets are insufficient, call read_full_document(file_path) to get full content
""".strip()

RAG_PROMPT_NO_TOOLS = """
## Retrieved Documentation
The following was automatically retrieved based on the user's query:

<retrieved_documents>
{context}
</retrieved_documents>

## RAG Instructions
- Use the retrieved context ONLY if it's relevant to the question
- If the context is irrelevant, ignore it and answer based on your knowledge
- When using context, cite sources: [Source: filename]
""".strip()
