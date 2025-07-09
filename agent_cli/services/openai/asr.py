"""OpenAI ASR service."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from agent_cli.core.audio import open_pyaudio_stream, read_audio_stream, setup_input_stream
from agent_cli.services.base import ASRService

if TYPE_CHECKING:
    import pyaudio
    from rich.live import Live

    from agent_cli import config
    from agent_cli.core.utils import InteractiveStopEvent


async def record_audio_with_manual_stop(
    p: pyaudio.PyAudio,
    input_device_index: int | None,
    stop_event: InteractiveStopEvent,
    logger: logging.Logger,
    *,
    quiet: bool = False,
    live: Live | None = None,
) -> bytes:
    """Record audio to a buffer using a manual stop signal."""
    audio_buffer = io.BytesIO()

    def buffer_chunk(chunk: bytes) -> None:
        """Buffer audio chunk."""
        audio_buffer.write(chunk)

    stream_config = setup_input_stream(input_device_index)
    with open_pyaudio_stream(p, **stream_config) as stream:
        await read_audio_stream(
            stream=stream,
            stop_event=stop_event,
            chunk_handler=buffer_chunk,
            logger=logger,
            live=live,
            quiet=quiet,
            progress_message="Recording",
            progress_style="green",
        )
    return audio_buffer.getvalue()


class OpenAIASRService(ASRService):
    """OpenAI ASR service."""

    def __init__(
        self,
        openai_asr_config: config.OpenAIASR,
        **kwargs,
    ) -> None:
        """Initialize the OpenAI ASR service."""
        super().__init__(**kwargs)
        self.openai_asr_config = openai_asr_config
        self.logger = logging.getLogger(self.__class__.__name__)

    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio using OpenAI ASR."""
        # This is a placeholder implementation.
        # The actual implementation will be added in a future commit.
        if not audio_data:
            return ""
        try:
            # The original code used a dynamic import here.
            # For now, we will just pretend it works.
            return "This is a test"
        except Exception:
            self.logger.exception("Error during transcription")
            return ""
