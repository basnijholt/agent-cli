"""Tool definitions for the chat agent."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable


# Memory system helpers


def _get_memory_file_path() -> Path:
    """Get the path to the memory file.

    If the environment variable ``AGENT_CLI_HISTORY_DIR`` is set (by the
    running agent), store the memory file in that directory.
    Otherwise fall back to the user's config directory.
    """
    history_dir = os.getenv("AGENT_CLI_HISTORY_DIR")
    if history_dir:
        return Path(history_dir).expanduser() / "long_term_memory.json"

    return Path.home() / ".config" / "agent-cli" / "memory" / "long_term_memory.json"


def _load_memories() -> list[dict[str, Any]]:
    """Load memories from file, returning empty list if file doesn't exist."""
    memory_file = _get_memory_file_path()
    if not memory_file.exists():
        return []

    with memory_file.open("r") as f:
        return json.load(f)


def _save_memories(memories: list[dict[str, Any]]) -> None:
    """Save memories to file, creating directories if needed."""
    memory_file = _get_memory_file_path()
    memory_file.parent.mkdir(parents=True, exist_ok=True)

    with memory_file.open("w") as f:
        json.dump(memories, f, indent=2)


def _find_memory_by_id(memories: list[dict[str, Any]], memory_id: int) -> dict[str, Any] | None:
    """Find a memory by ID in the memories list."""
    for memory in memories:
        if memory["id"] == memory_id:
            return memory
    return None


def _format_memory_summary(memory: dict[str, Any]) -> str:
    """Format a memory for display in search results."""
    return (
        f"ID: {memory['id']} | Category: {memory['category']} | "
        f"Content: {memory['content']} | Tags: {', '.join(memory['tags'])}"
    )


def _format_memory_detailed(memory: dict[str, Any]) -> str:
    """Format a memory with full details for listing."""
    created = datetime.fromisoformat(memory["timestamp"]).strftime("%Y-%m-%d %H:%M")
    updated_info = ""
    if "updated_at" in memory:
        updated = datetime.fromisoformat(memory["updated_at"]).strftime("%Y-%m-%d %H:%M")
        updated_info = f" (updated: {updated})"

    return (
        f"ID: {memory['id']} | Category: {memory['category']}\n"
        f"Content: {memory['content']}\n"
        f"Tags: {', '.join(memory['tags']) if memory['tags'] else 'None'}\n"
        f"Created: {created}{updated_info}\n"
    )


def _parse_tags(tags_string: str) -> list[str]:
    """Parse comma-separated tags string into a list of clean tags."""
    return [tag.strip() for tag in tags_string.split(",") if tag.strip()]


R = TypeVar("R")


def _memory_operation(operation_name: str, operation_func: Callable[[], str]) -> str:
    """Wrapper for memory operations with consistent error handling."""
    try:
        return operation_func()
    except Exception as e:
        return f"Error {operation_name}: {e}"


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
        Confirmation message with the memory ID

    """

    def _add_memory_operation() -> str:
        memories = _load_memories()

        memory = {
            "id": len(memories) + 1,
            "content": content,
            "category": category,
            "tags": _parse_tags(tags),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        memories.append(memory)
        _save_memories(memories)

        return f"Memory added successfully with ID {memory['id']}"

    return _memory_operation("adding memory", _add_memory_operation)


def search_memory(query: str, category: str = "") -> str:
    """Search long-term memory for relevant information before answering questions.

    Use this tool:
    - Before answering questions about the user's preferences, personal info, or past conversations
    - When the user asks "what do you remember about..." or similar questions
    - When you need context about the user's work, projects, or goals
    - To check if you've discussed a topic before

    The search looks through memory content and tags for matches.

    Args:
        query: Keywords to search for (e.g., "programming languages", "work schedule", "preferences")
        category: Optional filter by category ("personal", "preferences", "facts", "tasks", "projects")

    Returns:
        Relevant memories found, or message if none found

    """

    def _search_memory_operation() -> str:
        memories = _load_memories()

        if not memories:
            return "No memories found. Memory system not initialized."

        # Simple text-based search
        query_lower = query.lower()
        relevant_memories = []

        for memory in memories:
            # Check if query matches content, tags, or category
            content_match = query_lower in memory["content"].lower()
            tag_match = any(query_lower in tag.lower() for tag in memory["tags"])
            category_match = not category or memory["category"].lower() == category.lower()

            if (content_match or tag_match) and category_match:
                relevant_memories.append(memory)

        if not relevant_memories:
            return f"No memories found matching '{query}'"

        # Format results
        results = [_format_memory_summary(memory) for memory in relevant_memories[-5:]]

        return "\n".join(results)

    return _memory_operation("searching memory", _search_memory_operation)


def update_memory(memory_id: int, content: str = "", category: str = "", tags: str = "") -> str:
    """Update an existing memory by ID.

    Use this tool:
    - When the user wants to correct or modify previously stored information
    - When information has changed (e.g., job change, preference updates)
    - When the user says "update my memory about..." or "change the memory where..."

    Only provide the fields that should be updated - empty fields will keep existing values.

    Args:
        memory_id: The ID of the memory to update (use search_memory or list_all_memories to find IDs)
        content: New content for the memory (leave empty to keep existing)
        category: New category (leave empty to keep existing)
        tags: New comma-separated tags (leave empty to keep existing)

    Returns:
        Confirmation message or error if memory ID not found

    """

    def _update_memory_operation() -> str:
        memories = _load_memories()

        if not memories:
            return "No memories found. Memory system not initialized."

        # Find memory to update
        memory_to_update = _find_memory_by_id(memories, memory_id)
        if not memory_to_update:
            return f"Memory with ID {memory_id} not found."

        # Update fields if provided
        if content:
            memory_to_update["content"] = content
        if category:
            memory_to_update["category"] = category
        if tags:
            memory_to_update["tags"] = _parse_tags(tags)

        # Add update timestamp
        memory_to_update["updated_at"] = datetime.now(UTC).isoformat()

        _save_memories(memories)
        return f"Memory ID {memory_id} updated successfully."

    return _memory_operation("updating memory", _update_memory_operation)


def list_all_memories(limit: int = 10) -> str:
    """List all memories with their details.

    Use this tool:
    - When the user asks "show me all my memories" or "list everything you remember"
    - When they want to see specific memory IDs for updating or reference
    - To provide a complete overview of stored information

    Shows memories in reverse chronological order (newest first).

    Args:
        limit: Maximum number of memories to show (default 10, use higher numbers if user wants more)

    Returns:
        Formatted list of all memories with IDs, content, categories, and tags

    """

    def _list_all_memories_operation() -> str:
        memories = _load_memories()

        if not memories:
            return "No memories stored yet."

        # Sort by ID (newest first) and limit results
        memories_to_show = sorted(memories, key=lambda x: x["id"], reverse=True)[:limit]

        results = [f"Showing {len(memories_to_show)} of {len(memories)} total memories:\n"]
        results.extend(_format_memory_detailed(memory) for memory in memories_to_show)

        if len(memories) > limit:
            results.append(
                f"... and {len(memories) - limit} more memories. Use a higher limit to see more.",
            )

        return "\n".join(results)

    return _memory_operation("listing memories", _list_all_memories_operation)


def list_memory_categories() -> str:
    """List all memory categories and their counts to see what has been remembered.

    Use this tool:
    - When the user asks "what categories do you have?"
    - To get a quick overview of memory organization
    - When the user wants to know what types of information are stored

    This provides a summary view before using list_all_memories for details.

    Returns:
        Summary of memory categories with counts (e.g., "personal: 5 memories")

    """

    def _list_categories_operation() -> str:
        memories = _load_memories()

        if not memories:
            return "No memories found. Memory system not initialized."

        # Count categories
        categories: dict[str, int] = {}
        for memory in memories:
            category = memory["category"]
            categories[category] = categories.get(category, 0) + 1

        if not categories:
            return "No memory categories found."

        results = ["Memory Categories:"]
        for category, count in sorted(categories.items()):
            results.append(f"- {category}: {count} memories")

        return "\n".join(results)

    return _memory_operation("listing categories", _list_categories_operation)


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
