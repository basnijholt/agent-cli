"""Local ASR service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from wyoming.asr import Transcribe, Transcript, TranscriptChunk
from wyoming.audio import AudioChunk, AudioStart, AudioStop

from agent_cli import constants
from agent_cli.services._wyoming_utils import wyoming_client_context
from agent_cli.services.base import ASRService

if TYPE_CHECKING:
    from collections.abc import Callable

    from wyoming.client import AsyncClient

    from agent_cli import config


async def _receive_transcript(
    client: AsyncClient,
    logger: logging.Logger,
    *,
    chunk_callback: Callable[[str], None] | None = None,
    final_callback: Callable[[str], None] | None = None,
) -> str:
    """Receive transcription events and return the final transcript."""
    transcript_text = ""
    while True:
        event = await client.read_event()
        if event is None:
            logger.warning("Connection to ASR server lost.")
            break

        if Transcript.is_type(event.type):
            transcript = Transcript.from_event(event)
            transcript_text = transcript.text
            logger.info("Final transcript: %s", transcript_text)
            if final_callback:
                final_callback(transcript_text)
            break
        if TranscriptChunk.is_type(event.type):
            chunk = TranscriptChunk.from_event(event)
            logger.debug("Transcript chunk: %s", chunk.text)
            if chunk_callback:
                chunk_callback(chunk.text)
        else:
            logger.debug("Ignoring event type: %s", event.type)

    return transcript_text


class WyomingASRService(ASRService):
    """Wyoming ASR service."""

    def __init__(self, wyoming_asr_config: config.WyomingASR, **kwargs) -> None:
        """Initialize the Wyoming ASR service."""
        super().__init__(**kwargs)
        self.wyoming_asr_config = wyoming_asr_config
        self.logger = logging.getLogger(self.__class__.__name__)

    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio using Wyoming ASR."""
        try:
            async with wyoming_client_context(
                self.wyoming_asr_config.wyoming_asr_ip,
                self.wyoming_asr_config.wyoming_asr_port,
                "ASR",
                self.logger,
                quiet=self.is_interactive,
            ) as client:
                await client.write_event(Transcribe().event())
                await client.write_event(AudioStart(**constants.WYOMING_AUDIO_CONFIG).event())

                if audio_data:
                    chunk_size = constants.PYAUDIO_CHUNK_SIZE * 2
                    for i in range(0, len(audio_data), chunk_size):
                        chunk = audio_data[i : i + chunk_size]
                        await client.write_event(
                            AudioChunk(audio=chunk, **constants.WYOMING_AUDIO_CONFIG).event(),
                        )
                        self.logger.debug("Sent %d byte(s) of audio", len(chunk))

                await client.write_event(AudioStop().event())
                self.logger.debug("Sent AudioStop")

                return await _receive_transcript(client, self.logger)
        except (ConnectionRefusedError, Exception):
            return ""
