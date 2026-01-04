"""Tool definitions for the chat agent."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_cli.memory.client import MemoryClient


# --- Memory System State ---
# These module-level variables are set by init_memory() when the chat agent starts.

_memory_client: MemoryClient | None = None
_conversation_id: str = "default"
_event_loop: asyncio.AbstractEventLoop | None = None


def init_memory(
    client: MemoryClient,
    conversation_id: str = "default",
    event_loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """Initialize the memory system.

    Called by the chat agent on startup.

    Args:
        client: The MemoryClient instance to use for memory operations.
        conversation_id: The conversation ID for scoping memories.
        event_loop: The asyncio event loop for running async operations.

    """
    global _memory_client, _conversation_id, _event_loop
    _memory_client = client
    _conversation_id = conversation_id
    _event_loop = event_loop


async def cleanup_memory() -> None:
    """Clean up the memory system.

    Called when the chat agent exits.
    """
    global _memory_client, _event_loop
    if _memory_client is not None:
        await _memory_client.stop()
        _memory_client = None
    _event_loop = None


def _run_async(coro: Any, timeout: float = 30.0) -> Any:
    """Run an async coroutine from sync context using the stored event loop."""
    if _event_loop is None:
        msg = "Event loop not initialized for memory system"
        raise RuntimeError(msg)

    future = asyncio.run_coroutine_threadsafe(coro, _event_loop)
    return future.result(timeout=timeout)


def _check_memory_initialized() -> str | None:
    """Check if memory is initialized. Returns error message if not, None if OK."""
    if _memory_client is None:
        return "Error: Memory system not initialized. Install with: pip install 'agent-cli[memory]'"
    return None


def read_file(path: str) -> str:
    """Read the content of a file.

    Args:
        path: The path to the file to read.

    """
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        return f"Error: File not found at {path}"
    except OSError as e:
        return f"Error reading file: {e}"


def execute_code(code: str) -> str:
    """Execute a shell command.

    Args:
        code: The shell command to execute.

    """
    try:
        result = subprocess.run(
            code.split(),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error executing code: {e.stderr}"
    except FileNotFoundError:
        return f"Error: Command not found: {code.split()[0]}"


def add_memory(content: str, category: str = "general", tags: str = "") -> str:
    """Add important information to long-term memory for future conversations.

    Use this when the user shares:
    - Personal information (name, job, location, family, etc.)
    - Preferences (favorite foods, work style, communication preferences, etc.)
    - Important facts they want remembered (birthdays, project details, goals, etc.)
    - Tasks or commitments they mention

    Always ask for permission before storing personal or sensitive information.

    Args:
        content: The specific information to remember (be descriptive and clear)
        category: Type of memory - use "personal", "preferences", "facts", "tasks", "projects", or "general"
        tags: Comma-separated keywords that would help find this memory later (e.g., "work, python, programming")

    Returns:
        Confirmation message

    """
    if error := _check_memory_initialized():
        return error

    # Format content with metadata
    formatted_content = f"[{category}] {content}"
    if tags:
        formatted_content += f" (tags: {tags})"

    try:
        _run_async(_memory_client.add(formatted_content, conversation_id=_conversation_id))  # type: ignore[union-attr]
        return "Memory added successfully."
    except Exception as e:
        return f"Error adding memory: {e}"


def search_memory(query: str, category: str = "") -> str:
    """Search long-term memory for relevant information before answering questions.

    Use this tool:
    - Before answering questions about the user's preferences, personal info, or past conversations
    - When the user asks "what do you remember about..." or similar questions
    - When you need context about the user's work, projects, or goals
    - To check if you've discussed a topic before

    This performs semantic search to find conceptually related information.

    Args:
        query: Keywords to search for (e.g., "programming languages", "work schedule", "preferences")
        category: Optional filter by category ("personal", "preferences", "facts", "tasks", "projects")

    Returns:
        Relevant memories found, or message if none found

    """
    if error := _check_memory_initialized():
        return error

    # Include category in search query if provided
    search_query = f"{category} {query}" if category else query

    try:
        result = _run_async(
            _memory_client.search(search_query, conversation_id=_conversation_id),  # type: ignore[union-attr]
        )
        if not result.entries:
            return f"No memories found matching '{query}'"

        # Format results with relevance scores
        lines = []
        for entry in result.entries:
            score_info = f" (relevance: {entry.score:.2f})" if entry.score else ""
            lines.append(f"- {entry.content}{score_info}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error searching memory: {e}"


def update_memory(memory_id: int, content: str = "", category: str = "", tags: str = "") -> str:
    """Update an existing memory by adding new information.

    Use this tool:
    - When the user wants to correct or modify previously stored information
    - When information has changed (e.g., job change, preference updates)
    - When the user says "update my memory about..." or "change the memory where..."

    The memory system uses automatic reconciliation - adding new information will
    update or replace related existing facts.

    Args:
        memory_id: Not used - the system automatically reconciles memories
        content: The updated content to store
        category: Category for the memory (leave empty for "general")
        tags: Comma-separated tags (leave empty for none)

    Returns:
        Confirmation message

    """
    _ = memory_id  # System uses reconciliation, not ID-based updates

    if error := _check_memory_initialized():
        return error

    if not content:
        return "Please provide the updated content. The system will automatically reconcile it with existing memories."

    # Format content with metadata
    formatted_content = f"[{category or 'general'}] {content}"
    if tags:
        formatted_content += f" (tags: {tags})"

    try:
        _run_async(_memory_client.add(formatted_content, conversation_id=_conversation_id))  # type: ignore[union-attr]
        return "Memory updated successfully. The system has reconciled this information with existing memories."
    except Exception as e:
        return f"Error updating memory: {e}"


def list_all_memories(limit: int = 10) -> str:
    """List all memories with their details.

    Use this tool:
    - When the user asks "show me all my memories" or "list everything you remember"
    - When they want to see what information is stored
    - To provide a complete overview of stored information

    Shows memories in reverse chronological order (newest first).

    Args:
        limit: Maximum number of memories to show (default 10, use higher numbers if user wants more)

    Returns:
        Formatted list of all memories

    """
    if error := _check_memory_initialized():
        return error

    try:
        entries = _memory_client.list_all(  # type: ignore[union-attr]
            conversation_id=_conversation_id,
            include_summary=False,
        )

        if not entries:
            return "No memories stored yet."

        # Limit results
        entries_to_show = entries[:limit]

        results = [f"Showing {len(entries_to_show)} of {len(entries)} total memories:\n"]
        for entry in entries_to_show:
            created_at = entry.get("created_at", "unknown")
            role = entry.get("role", "memory")
            content = entry.get("content", "")
            results.append(f"- [{role}] {content} (created: {created_at})")

        if len(entries) > limit:
            results.append(
                f"\n... and {len(entries) - limit} more memories. Use a higher limit to see more.",
            )

        return "\n".join(results)
    except Exception as e:
        return f"Error listing memories: {e}"


def list_memory_categories() -> str:
    """List all memory categories and their counts to see what has been remembered.

    Use this tool:
    - When the user asks "what categories do you have?"
    - To get a quick overview of memory organization
    - When the user wants to know what types of information are stored

    This provides a summary view before using list_all_memories for details.

    Returns:
        Summary of memory types with counts

    """
    if error := _check_memory_initialized():
        return error

    try:
        entries = _memory_client.list_all(  # type: ignore[union-attr]
            conversation_id=_conversation_id,
            include_summary=False,
        )

        if not entries:
            return "No memories found."

        # Count by role (user, assistant, memory)
        roles: dict[str, int] = {}
        for entry in entries:
            role = entry.get("role", "memory")
            roles[role] = roles.get(role, 0) + 1

        results = ["Memory Types:"]
        for role, count in sorted(roles.items()):
            results.append(f"- {role}: {count} entries")

        return "\n".join(results)
    except Exception as e:
        return f"Error listing categories: {e}"


def tools() -> list:
    """Return a list of tools."""
    from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool  # noqa: PLC0415
    from pydantic_ai.tools import Tool  # noqa: PLC0415

    return [
        Tool(read_file),
        Tool(execute_code),
        Tool(add_memory),
        Tool(search_memory),
        Tool(update_memory),
        Tool(list_all_memories),
        Tool(list_memory_categories),
        duckduckgo_search_tool(),
    ]
