"""Type definitions for services."""

from typing import TypedDict


class ChatMessage(TypedDict):
    """A single entry in the conversation."""

    role: str
    content: str
    timestamp: str
