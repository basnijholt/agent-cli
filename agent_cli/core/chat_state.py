"""Chat session state and slash command handling.

This module provides state management for interactive chat sessions
and handles slash commands like /tts, /mode, /tools, /clear, /help.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from agent_cli.agents.chat import ConversationEntry

# Available tools that can be toggled
AVAILABLE_TOOLS = frozenset(
    {
        "read_file",
        "execute_code",
        "add_memory",
        "search_memory",
        "update_memory",
        "list_all_memories",
        "list_memory_categories",
        "duckduckgo_search",
    },
)


@dataclass
class ChatSessionState:
    """Runtime state for an interactive chat session."""

    tts_enabled: bool = True
    input_mode: Literal["live", "direct"] = "live"
    disabled_tools: set[str] = field(default_factory=set)
    conversation_history: list[ConversationEntry] = field(default_factory=list)

    def toggle_tts(self) -> bool:
        """Toggle TTS and return new state."""
        self.tts_enabled = not self.tts_enabled
        return self.tts_enabled

    def set_tts(self, enabled: bool) -> None:
        """Set TTS state explicitly."""
        self.tts_enabled = enabled

    def set_mode(self, mode: Literal["live", "direct"]) -> None:
        """Set input mode."""
        self.input_mode = mode

    def disable_tool(self, tool_name: str) -> bool:
        """Disable a tool. Returns True if successful, False if tool not found."""
        if tool_name not in AVAILABLE_TOOLS:
            return False
        self.disabled_tools.add(tool_name)
        return True

    def enable_tool(self, tool_name: str) -> bool:
        """Enable a tool. Returns True if successful, False if tool not found."""
        if tool_name not in AVAILABLE_TOOLS:
            return False
        self.disabled_tools.discard(tool_name)
        return True

    def clear_history(self) -> int:
        """Clear conversation history. Returns number of messages cleared."""
        count = len(self.conversation_history)
        self.conversation_history.clear()
        return count


def parse_slash_command(text: str) -> tuple[str, list[str]] | None:
    """Parse a slash command from text.

    Args:
        text: The input text to parse

    Returns:
        Tuple of (command, args) if it's a slash command, None otherwise

    """
    text = text.strip()
    if not text.startswith("/"):
        return None

    parts = text[1:].split()
    if not parts:
        return None

    command = parts[0].lower()
    args = parts[1:]
    return command, args


def handle_slash_command(
    command: str,
    args: list[str],
    state: ChatSessionState,
) -> str:
    """Execute a slash command and return a response message.

    Args:
        command: The command name (without slash)
        args: Command arguments
        state: The chat session state

    Returns:
        Response message to display to the user

    """
    if command == "help":
        return _handle_help()

    if command == "tts":
        return _handle_tts(args, state)

    if command == "mode":
        return _handle_mode(args, state)

    if command == "tools":
        return _handle_tools(args, state)

    if command == "clear":
        return _handle_clear(state)

    return f"Unknown command: /{command}. Type /help for available commands."


def _handle_help() -> str:
    """Show help message."""
    return """\
Available commands:
  /tts           Toggle TTS on/off
  /tts on|off    Set TTS state explicitly
  /mode live     Live transcription mode (default)
  /mode direct   Direct voice mode (speak until Ctrl+C)
  /tools         List all tools and their status
  /tools disable <name>  Disable a tool
  /tools enable <name>   Enable a tool
  /clear         Clear conversation history
  /help          Show this help message

Keyboard shortcuts:
  Escape         Pause/resume microphone
  Enter          Send message
  Ctrl+C         Exit chat"""


def _handle_tts(args: list[str], state: ChatSessionState) -> str:
    """Handle /tts command."""
    if not args:
        new_state = state.toggle_tts()
        status = "on" if new_state else "off"
        return f"TTS is now {status}"

    arg = args[0].lower()
    if arg == "on":
        state.set_tts(enabled=True)
        return "TTS is now on"
    if arg == "off":
        state.set_tts(enabled=False)
        return "TTS is now off"
    return f"Invalid argument: {arg}. Use /tts, /tts on, or /tts off"


def _handle_mode(args: list[str], state: ChatSessionState) -> str:
    """Handle /mode command."""
    if not args:
        return f"Current mode: {state.input_mode}. Use /mode live or /mode direct"

    arg = args[0].lower()
    if arg == "live":
        state.set_mode("live")
        return "Switched to live mode (VAD + editable transcription)"
    if arg == "direct":
        state.set_mode("direct")
        return "Switched to direct mode (speak until Ctrl+C)"
    return f"Invalid mode: {arg}. Use /mode live or /mode direct"


def _handle_tools(args: list[str], state: ChatSessionState) -> str:
    """Handle /tools command."""
    if not args:
        # List all tools with status
        lines = ["Available tools:"]
        for tool in sorted(AVAILABLE_TOOLS):
            status = "disabled" if tool in state.disabled_tools else "enabled"
            marker = "✗" if tool in state.disabled_tools else "✓"
            lines.append(f"  {marker} {tool} ({status})")
        return "\n".join(lines)

    action = args[0].lower()

    if action in ("disable", "enable"):
        if len(args) < 2:  # noqa: PLR2004
            return f"Usage: /tools {action} <tool_name>"
        tool_name = args[1]
        success = (
            state.disable_tool(tool_name) if action == "disable" else state.enable_tool(tool_name)
        )
        if success:
            past_tense = "Disabled" if action == "disable" else "Enabled"
            return f"{past_tense} tool: {tool_name}"
        return f"Unknown tool: {tool_name}. Use /tools to see available tools."

    return f"Unknown action: {action}. Use /tools, /tools disable <name>, or /tools enable <name>"


def _handle_clear(state: ChatSessionState) -> str:
    """Handle /clear command."""
    count = state.clear_history()
    return f"Cleared {count} messages from conversation history"
