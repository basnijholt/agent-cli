"""Abstract base classes for services."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from agent_cli.core.utils import InteractiveStopEvent


class LLMService(ABC):
    """Abstract base class for LLM services."""

    def __init__(
        self,
        *,
        is_interactive: bool,
        stop_event: InteractiveStopEvent | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize the LLM service."""
        self.is_interactive = is_interactive
        self.stop_event = stop_event
        self.model = model

    @abstractmethod
    def chat(
        self,
        message: str,
        system_prompt: str | None = None,
        instructions: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Chat with the LLM."""
        ...


class ASRService(ABC):
    """Abstract base class for ASR services."""

    def __init__(
        self,
        *,
        is_interactive: bool,
        stop_event: InteractiveStopEvent | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize the ASR service."""
        self.is_interactive = is_interactive
        self.stop_event = stop_event
        self.model = model

    @abstractmethod
    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio."""
        ...


class TTSService(ABC):
    """Abstract base class for TTS services."""

    def __init__(
        self,
        *,
        is_interactive: bool,
        stop_event: InteractiveStopEvent | None = None,
        model: str | None = None,
        voice: str | None = None,
    ) -> None:
        """Initialize the TTS service."""
        self.is_interactive = is_interactive
        self.stop_event = stop_event
        self.model = model
        self.voice = voice

    @abstractmethod
    async def synthesise(self, text: str) -> bytes:
        """Synthesise text to speech."""
        ...
