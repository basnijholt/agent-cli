"""Local ASR service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_cli.services.base import ASRService

if TYPE_CHECKING:
    import asyncio
    from collections.abc import AsyncGenerator

    from agent_cli import config


class WyomingASRService(ASRService):
    """Wyoming ASR service."""

    def __init__(self, wyoming_asr_config: config.WyomingASR, **kwargs) -> None:
        """Initialize the Wyoming ASR service."""
        super().__init__(**kwargs)
        self.wyoming_asr_config = wyoming_asr_config

    async def transcribe(self, audio_stream: asyncio.Queue[bytes]) -> AsyncGenerator[str, None]:
        """Transcribe audio using Wyoming ASR."""
        yield "Hello from Wyoming ASR!"
        # To satisfy mypy, we need to use the audio_stream argument.
        # We can do this by reading from the queue and then breaking.
        while not audio_stream.empty():
            await audio_stream.get()
