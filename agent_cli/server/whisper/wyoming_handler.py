"""Wyoming protocol handler for Whisper ASR server."""

from __future__ import annotations

import io
import logging
import wave
from functools import partial
from typing import TYPE_CHECKING

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStop
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
from wyoming.server import AsyncEventHandler, AsyncServer

if TYPE_CHECKING:
    from wyoming.event import Event

    from agent_cli.server.whisper.model_registry import WhisperModelRegistry

logger = logging.getLogger(__name__)

# Language codes supported by Whisper
_LANGUAGE_CODES = [
    "af",
    "am",
    "ar",
    "as",
    "az",
    "ba",
    "be",
    "bg",
    "bn",
    "bo",
    "br",
    "bs",
    "ca",
    "cs",
    "cy",
    "da",
    "de",
    "el",
    "en",
    "es",
    "et",
    "eu",
    "fa",
    "fi",
    "fo",
    "fr",
    "gl",
    "gu",
    "ha",
    "haw",
    "he",
    "hi",
    "hr",
    "ht",
    "hu",
    "hy",
    "id",
    "is",
    "it",
    "ja",
    "jw",
    "ka",
    "kk",
    "km",
    "kn",
    "ko",
    "la",
    "lb",
    "ln",
    "lo",
    "lt",
    "lv",
    "mg",
    "mi",
    "mk",
    "ml",
    "mn",
    "mr",
    "ms",
    "mt",
    "my",
    "ne",
    "nl",
    "nn",
    "no",
    "oc",
    "pa",
    "pl",
    "ps",
    "pt",
    "ro",
    "ru",
    "sa",
    "sd",
    "si",
    "sk",
    "sl",
    "sn",
    "so",
    "sq",
    "sr",
    "su",
    "sv",
    "sw",
    "ta",
    "te",
    "tg",
    "th",
    "tk",
    "tl",
    "tr",
    "tt",
    "uk",
    "ur",
    "uz",
    "vi",
    "yi",
    "yo",
    "zh",
    "yue",
]


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
        self._audio_buffer: io.BytesIO | None = None
        self._wav_file: wave.Wave_write | None = None
        self._language: str | None = None

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
        chunk = AudioChunk.from_event(event)

        if self._wav_file is None:
            logger.debug("AudioChunk begin")
            self._audio_buffer = io.BytesIO()
            self._wav_file = wave.open(self._audio_buffer, "wb")  # noqa: SIM115
            self._wav_file.setframerate(chunk.rate)
            self._wav_file.setsampwidth(chunk.width)
            self._wav_file.setnchannels(chunk.channels)

        self._wav_file.writeframes(chunk.audio)
        return True

    async def _handle_audio_stop(self) -> bool:
        """Handle audio stop event - transcribe the collected audio."""
        logger.debug("AudioStop")

        if self._wav_file is None or self._audio_buffer is None:
            logger.warning("AudioStop received but no audio data")
            await self.write_event(Transcript(text="").event())
            return False

        # Close WAV file
        self._wav_file.close()
        self._wav_file = None

        # Get audio data
        self._audio_buffer.seek(0)
        audio_data = self._audio_buffer.read()
        self._audio_buffer = None

        # Transcribe
        try:
            manager = self._registry.get_manager()
            result = await manager.transcribe(
                audio_data,
                language=self._language,
                task="transcribe",
            )

            logger.info("Wyoming transcription: %s", result.text[:100] if result.text else "")
            await self.write_event(Transcript(text=result.text).event())

        except Exception:
            logger.exception("Wyoming transcription failed")
            await self.write_event(Transcript(text="").event())

        # Reset language for next request
        self._language = None
        return False

    def _handle_transcribe(self, event: Event) -> bool:
        """Handle transcribe event - sets language preference."""
        logger.debug("Transcribe event")
        transcribe = Transcribe.from_event(event)
        if transcribe.language:
            self._language = transcribe.language
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
                languages=_LANGUAGE_CODES,
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
    uri: str = "tcp://0.0.0.0:3001",
) -> None:
    """Start the Wyoming ASR server.

    Args:
        registry: Model registry for transcription.
        uri: URI to bind the server to (e.g., "tcp://0.0.0.0:3001").

    """
    server = AsyncServer.from_uri(uri)
    logger.info("Wyoming server listening on %s", uri)

    # Create handler factory with registry
    handler_factory = partial(WyomingWhisperHandler, registry)

    await server.run(handler_factory)
