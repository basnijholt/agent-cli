"""Base classes for external services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging

    from rich.live import Live

    from agent_cli import config


class ASRService(ABC):
    """Abstract base class for Automatic Speech Recognition services."""

    @abstractmethod
    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio data to text."""
        pass


class LLMService(ABC):
    """Abstract base class for Language Model services."""

    @abstractmethod
    async def get_response(
        self,
        *,
        system_prompt: str,
        agent_instructions: str,
        user_input: str,
        tools: list | None = None,
    ) -> str | None:
        """Get a response from the language model."""
        pass


class TTSService(ABC):
    """Abstract base class for Text-to-Speech services."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes | None:
        """Synthesize text to speech audio data."""
        pass


class WakeWordService(ABC):
    """Abstract base class for Wake Word detection services."""

    @abstractmethod
    async def detect(self) -> str | None:
        """Detect the wake word."""
        pass
