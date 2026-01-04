"""Tool definitions for the chat agent."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_cli.memory.client import MemoryClient


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


def _format_memory_content(content: str, category: str, tags: str) -> str:
    """Format memory content with category and tags."""
    formatted = f"[{category}] {content}"
    if tags:
        formatted += f" (tags: {tags})"
    return formatted


class MemoryTools:
    """Memory tools bound to a specific client and conversation."""

    def __init__(
        self,
        memory_client: MemoryClient | None,
        conversation_id: str = "default",
    ) -> None:
        self._client = memory_client
        self._conversation_id = conversation_id

    def _check(self) -> str | None:
        if self._client is None:
            return "Error: Memory system not initialized. Install with: pip install 'agent-cli[memory]'"
        return None

    async def add_memory(
        self,
        content: str,
        category: str = "general",
        tags: str = "",
    ) -> str:
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
        if error := self._check():
            return error

        try:
            formatted = _format_memory_content(content, category, tags)
            await self._client.add(formatted, conversation_id=self._conversation_id)  # type: ignore[union-attr]
            return "Memory added successfully."
        except Exception as e:
            return f"Error adding memory: {e}"

    async def search_memory(self, query: str, category: str = "") -> str:
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
        if error := self._check():
            return error

        search_query = f"{category} {query}" if category else query

        try:
            result = await self._client.search(search_query, conversation_id=self._conversation_id)  # type: ignore[union-attr]
            if not result.entries:
                return f"No memories found matching '{query}'"

            lines = []
            for entry in result.entries:
                score_info = f" (relevance: {entry.score:.2f})" if entry.score else ""
                lines.append(f"- {entry.content}{score_info}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error searching memory: {e}"

    def list_all_memories(self, limit: int = 10) -> str:
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
        if error := self._check():
            return error

        try:
            entries = self._client.list_all(  # type: ignore[union-attr]
                conversation_id=self._conversation_id,
                include_summary=False,
            )

            if not entries:
                return "No memories stored yet."

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

    def list_memory_categories(self) -> str:
        """List all memory categories and their counts to see what has been remembered.

        Use this tool:
        - When the user asks "what categories do you have?"
        - To get a quick overview of memory organization
        - When the user wants to know what types of information are stored

        This provides a summary view before using list_all_memories for details.

        Returns:
            Summary of memory types with counts

        """
        if error := self._check():
            return error

        try:
            entries = self._client.list_all(  # type: ignore[union-attr]
                conversation_id=self._conversation_id,
                include_summary=False,
            )

            if not entries:
                return "No memories found."

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


def create_memory_tools(
    memory_client: MemoryClient | None,
    conversation_id: str = "default",
) -> list:
    """Create memory tools bound to a specific client and conversation.

    Args:
        memory_client: The MemoryClient instance, or None if not available.
        conversation_id: The conversation ID for scoping memories.

    Returns:
        List of pydantic_ai Tool objects for memory operations.

    """
    from pydantic_ai.tools import Tool  # noqa: PLC0415

    mt = MemoryTools(memory_client, conversation_id)
    return [
        Tool(mt.add_memory),
        Tool(mt.search_memory),
        Tool(mt.list_all_memories),
        Tool(mt.list_memory_categories),
    ]


def tools(memory_client: MemoryClient | None = None, conversation_id: str = "default") -> list:
    """Return a list of all tools for the chat agent.

    Args:
        memory_client: The MemoryClient instance, or None if not available.
        conversation_id: The conversation ID for scoping memories.

    """
    from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool  # noqa: PLC0415
    from pydantic_ai.tools import Tool  # noqa: PLC0415

    return [
        Tool(read_file),
        Tool(execute_code),
        *create_memory_tools(memory_client, conversation_id),
        duckduckgo_search_tool(),
    ]
