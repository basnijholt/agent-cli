"""Wyoming protocol handler for Whisper ASR server."""

from __future__ import annotations

import logging
from functools import partial
from typing import TYPE_CHECKING

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStop
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
from wyoming.server import AsyncEventHandler, AsyncServer

from agent_cli import constants
from agent_cli.server.whisper.languages import WHISPER_LANGUAGE_CODES
from agent_cli.services import pcm_to_wav

if TYPE_CHECKING:
    from wyoming.event import Event

    from agent_cli.server.whisper.model_registry import WhisperModelRegistry

logger = logging.getLogger(__name__)


class WyomingWhisperHandler(AsyncEventHandler):
    """Wyoming event handler for Whisper ASR.

    Handles the Wyoming protocol for ASR (Automatic Speech Recognition):
    - Receives audio chunks
    - Transcribes audio when AudioStop is received
    - Returns transcript
    """

    def __init__(
        self,
        registry: WhisperModelRegistry,
        *args: object,
        **kwargs: object,
    ) -> None:
        """Initialize the handler.

        Args:
            registry: Model registry for getting transcription models.
            *args: Passed to parent class.
            **kwargs: Passed to parent class.

        """
        super().__init__(*args, **kwargs)
        self._registry = registry
        self._audio_bytes: bytes = b""
        self._audio_converter = AudioChunkConverter(
            rate=constants.AUDIO_RATE,
            width=constants.AUDIO_FORMAT_WIDTH,
            channels=constants.AUDIO_CHANNELS,
        )
        self._language: str | None = None
        self._initial_prompt: str | None = None

    async def handle_event(self, event: Event) -> bool:
        """Handle a Wyoming event.

        Args:
            event: The event to handle.

        Returns:
            True to continue processing events, False to stop.

        """
        if AudioChunk.is_type(event.type):
            return await self._handle_audio_chunk(event)

        if AudioStop.is_type(event.type):
            return await self._handle_audio_stop()

        if Transcribe.is_type(event.type):
            return self._handle_transcribe(event)

        if Describe.is_type(event.type):
            return await self._handle_describe()

        return True

    async def _handle_audio_chunk(self, event: Event) -> bool:
        """Handle an audio chunk event."""
        if not self._audio_bytes:
            logger.debug("AudioChunk begin")

        chunk = AudioChunk.from_event(event)
        chunk = self._audio_converter.convert(chunk)
        self._audio_bytes += chunk.audio
        return True

    async def _handle_audio_stop(self) -> bool:
        """Handle audio stop event - transcribe the collected audio."""
        logger.debug("AudioStop")

        if not self._audio_bytes:
            logger.warning("AudioStop received but no audio data")
            await self.write_event(Transcript(text="").event())
            return False

        # Wrap PCM in WAV format for the backend
        audio_data = pcm_to_wav(
            self._audio_bytes,
            sample_rate=constants.AUDIO_RATE,
            sample_width=constants.AUDIO_FORMAT_WIDTH,
            channels=constants.AUDIO_CHANNELS,
        )
        self._audio_bytes = b""

        # Transcribe
        try:
            manager = self._registry.get_manager()
            result = await manager.transcribe(
                audio_data,
                language=self._language,
                task="transcribe",
                initial_prompt=self._initial_prompt,
            )

            logger.info("Wyoming transcription: %s", result.text[:100] if result.text else "")
            await self.write_event(Transcript(text=result.text).event())

        except Exception:
            logger.exception("Wyoming transcription failed")
            await self.write_event(Transcript(text="").event())

        # Reset state for next request
        self._language = None
        self._initial_prompt = None
        return False

    def _handle_transcribe(self, event: Event) -> bool:
        """Handle transcribe event - sets language and prompt preferences."""
        logger.debug("Transcribe event")
        transcribe = Transcribe.from_event(event)
        if transcribe.language:
            self._language = transcribe.language
        # Extract initial_prompt from context if provided
        if transcribe.context and "initial_prompt" in transcribe.context:
            self._initial_prompt = transcribe.context["initial_prompt"]
            logger.debug("Using initial_prompt from context")
        return True

    async def _handle_describe(self) -> bool:
        """Handle describe event - return server capabilities."""
        logger.debug("Describe event")

        # Get list of available models
        models = [
            AsrModel(
                name=status.name,
                description=f"Whisper {status.name}",
                attribution=Attribution(
                    name="OpenAI",
                    url="https://github.com/openai/whisper",
                ),
                installed=True,
                languages=WHISPER_LANGUAGE_CODES,
                version="1.0",
            )
            for status in self._registry.list_status()
        ]

        await self.write_event(
            Info(
                asr=[
                    AsrProgram(
                        name="agent-cli-whisper",
                        description="Agent CLI Whisper ASR Server with TTL-based model unloading",
                        attribution=Attribution(
                            name="agent-cli",
                            url="https://github.com/basnijholt/agent-cli",
                        ),
                        installed=True,
                        version="1.0",
                        models=models,
                    ),
                ],
            ).event(),
        )
        return True


async def start_wyoming_server(
    registry: WhisperModelRegistry,
    uri: str = "tcp://0.0.0.0:10300",
) -> None:
    """Start the Wyoming ASR server.

    Args:
        registry: Model registry for transcription.
        uri: URI to bind the server to (e.g., "tcp://0.0.0.0:10300").

    """
    server = AsyncServer.from_uri(uri)
    logger.debug("Wyoming server listening on %s", uri)

    # Create handler factory with registry
    handler_factory = partial(WyomingWhisperHandler, registry)

    await server.run(handler_factory)
