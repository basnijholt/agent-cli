"""Mock Wyoming servers and clients for testing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from wyoming.asr import Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop

from agent_cli import constants

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from wyoming.event import Event


class MockWyomingClient:
    """Base class for mock Wyoming clients."""

    def __init__(self) -> None:
        """Initialize mock client."""
        self.events_written: list[Event] = []
        self.is_active = True

    async def write_event(self, event: Event) -> None:
        """Mock writing an event."""
        if self.is_active:
            self.events_written.append(event)

    async def read_event(self) -> Event | None:
        """Mock reading an event."""
        raise NotImplementedError

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        self.is_active = False


class MockASRClient(MockWyomingClient):
    """Mock Wyoming ASR client for testing transcription."""

    def __init__(self, transcript_text: str) -> None:
        """Initialize mock ASR client."""
        super().__init__()
        self.transcript_text = transcript_text
        self._event_generator = self._generate_events()

    async def read_event(self) -> Event | None:
        """Mock reading events from the server."""
        try:
            return await self._event_generator.__anext__()
        except StopAsyncIteration:
            return None

    async def _generate_events(self) -> AsyncGenerator[Event, None]:
        """Generate transcript events."""
        yield Transcript(text=self.transcript_text).event()


class MockTTSClient(MockWyomingClient):
    """Mock Wyoming TTS client for testing speech synthesis."""

    def __init__(self, audio_data: bytes) -> None:
        """Initialize mock TTS client."""
        super().__init__()
        self.audio_data = audio_data
        self._event_generator = self._generate_events()

    async def read_event(self) -> Event | None:
        """Mock reading events from the server."""
        try:
            return await self._event_generator.__anext__()
        except StopAsyncIteration:
            return None

    async def _generate_events(self) -> AsyncGenerator[Event, None]:
        """Generate audio synthesis events."""
        yield AudioStart(
            rate=constants.PIPER_DEFAULT_SAMPLE_RATE,
            width=2,
            channels=1,
        ).event()
        yield AudioChunk(
            rate=constants.PIPER_DEFAULT_SAMPLE_RATE,
            width=2,
            channels=1,
            audio=self.audio_data,
        ).event()
        yield AudioStop().event()

    async def connect(self) -> None:
        """Mock connect."""

    async def disconnect(self) -> None:
        """Mock disconnect."""
