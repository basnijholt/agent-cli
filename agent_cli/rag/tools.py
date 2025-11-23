"""Tools for RAG agent."""

from __future__ import annotations

from pydantic_ai import RunContext  # noqa: TC002

from agent_cli.rag.models import RAGDeps  # noqa: TC001
from agent_cli.rag.utils import load_document_text


def read_full_document(ctx: RunContext[RAGDeps], file_path: str) -> str:
    """Read the full content of a document.

    Use this tool when the context provided in the prompt is not enough
    and you need to read the entire file to answer the user's question.
    The `file_path` should be exactly as it appears in the `[Source: ...]` tag.

    Args:
        ctx: The run context.
        file_path: The relative path to the file.

    """
    try:
        # Security check: resolve path and ensure it's inside docs_folder
        # We assume file_path is relative to docs_folder

        # Prevent absolute paths or traversal
        if ".." in file_path or file_path.startswith("/"):
            # Simple check, but we'll do robust check below
            pass

        docs_folder = ctx.deps.docs_folder.resolve()
        # Join and resolve
        full_path = (docs_folder / file_path).resolve()

        # Verify it is still inside docs_folder
        if not str(full_path).startswith(str(docs_folder)):
            return "Error: Access denied. Path is outside the document folder."

        if not full_path.exists():
            return f"Error: File not found: {file_path}"

        text = load_document_text(full_path)
        if text is None:
            return "Error: Could not read file (unsupported format or encoding)."

        return text

    except Exception as e:
        return f"Error reading file: {e}"
