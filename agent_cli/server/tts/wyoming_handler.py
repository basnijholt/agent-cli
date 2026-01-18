"""Wyoming protocol handler for TTS server."""

from __future__ import annotations

import logging
from functools import partial
from typing import TYPE_CHECKING

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import Synthesize

from agent_cli import constants

if TYPE_CHECKING:
    from wyoming.event import Event

    from agent_cli.server.tts.model_manager import TTSModelManager
    from agent_cli.server.tts.model_registry import TTSModelRegistry

logger = logging.getLogger(__name__)


class WyomingTTSHandler(AsyncEventHandler):
    """Wyoming event handler for TTS.

    Handles the Wyoming protocol for TTS (Text-to-Speech):
    - Receives Synthesize event with text
    - Synthesizes audio
    - Returns AudioStart, AudioChunk(s), AudioStop
    """

    def __init__(
        self,
        registry: TTSModelRegistry,
        *args: object,
        **kwargs: object,
    ) -> None:
        """Initialize the handler.

        Args:
            registry: Model registry for getting TTS models.
            *args: Passed to parent class.
            **kwargs: Passed to parent class.

        """
        super().__init__(*args, **kwargs)
        self._registry = registry

    async def handle_event(self, event: Event) -> bool:
        """Handle a Wyoming event.

        Args:
            event: The event to handle.

        Returns:
            True to continue processing events, False to stop.

        """
        if Synthesize.is_type(event.type):
            return await self._handle_synthesize(event)

        if Describe.is_type(event.type):
            return await self._handle_describe()

        return True

    async def _handle_synthesize(self, event: Event) -> bool:
        """Handle synthesize event - synthesize text to audio."""
        synthesize = Synthesize.from_event(event)
        text = synthesize.text

        logger.debug("Synthesize: %s", text[:100] if text else "")

        if not text:
            logger.warning("Empty text received")
            # Send empty audio response
            await self.write_event(
                AudioStart(
                    rate=constants.PIPER_DEFAULT_SAMPLE_RATE,
                    width=2,
                    channels=1,
                ).event(),
            )
            await self.write_event(AudioStop().event())
            return False

        try:
            manager = self._registry.get_manager()

            if manager.supports_streaming:
                await self._synthesize_streaming(manager, text, synthesize.voice)
            else:
                await self._synthesize_complete(manager, text, synthesize.voice)

        except Exception:
            logger.exception("Wyoming synthesis failed")
            # Send empty audio on error
            await self.write_event(
                AudioStart(
                    rate=constants.PIPER_DEFAULT_SAMPLE_RATE,
                    width=2,
                    channels=1,
                ).event(),
            )
            await self.write_event(AudioStop().event())

        return False

    async def _synthesize_streaming(
        self,
        manager: TTSModelManager,
        text: str,
        voice: str | None,
    ) -> None:
        """Stream audio chunks as they're generated."""
        sample_rate = constants.KOKORO_DEFAULT_SAMPLE_RATE

        # Send audio start
        await self.write_event(
            AudioStart(rate=sample_rate, width=2, channels=1).event(),
        )

        chunk_count = 0
        total_bytes = 0
        async for chunk in manager.synthesize_stream(text, voice=voice, speed=1.0):
            await self.write_event(
                AudioChunk(audio=chunk, rate=sample_rate, width=2, channels=1).event(),
            )
            chunk_count += 1
            total_bytes += len(chunk)

        await self.write_event(AudioStop().event())

        # Calculate duration from PCM bytes (16-bit mono)
        duration = total_bytes / (sample_rate * 2)
        logger.info(
            "Wyoming streaming synthesis: %d chars -> %.1fs audio in %d chunks",
            len(text),
            duration,
            chunk_count,
        )

    async def _synthesize_complete(
        self,
        manager: TTSModelManager,
        text: str,
        voice: str | None,
    ) -> None:
        """Synthesize complete audio then send in chunks."""
        result = await manager.synthesize(text, voice=voice, speed=1.0)

        # Send audio start
        await self.write_event(
            AudioStart(
                rate=result.sample_rate,
                width=result.sample_width,
                channels=result.channels,
            ).event(),
        )

        # Send audio data - skip WAV header to get raw PCM
        pcm_data = (
            result.audio[constants.WAV_HEADER_SIZE :]
            if len(result.audio) > constants.WAV_HEADER_SIZE
            else result.audio
        )

        # Send in chunks
        chunk_size = 4096
        for i in range(0, len(pcm_data), chunk_size):
            chunk = pcm_data[i : i + chunk_size]
            await self.write_event(
                AudioChunk(
                    audio=chunk,
                    rate=result.sample_rate,
                    width=result.sample_width,
                    channels=result.channels,
                ).event(),
            )

        await self.write_event(AudioStop().event())

        logger.info(
            "Wyoming synthesis: %d chars -> %.1fs audio",
            len(text),
            result.duration,
        )

    async def _handle_describe(self) -> bool:
        """Handle describe event - return server capabilities."""
        logger.debug("Describe event")

        # Get list of available models as voices
        voices = [
            TtsVoice(
                name=status.name,
                description=f"Piper TTS {status.name}",
                attribution=Attribution(
                    name="Piper",
                    url="https://github.com/rhasspy/piper",
                ),
                installed=True,
                # Extract language from model name (e.g., "en_US-lessac-medium" -> "en")
                languages=[status.name.split("_")[0] if "_" in status.name else "en"],
                version="1.0",
            )
            for status in self._registry.list_status()
        ]

        await self.write_event(
            Info(
                tts=[
                    TtsProgram(
                        name="agent-cli-tts",
                        description="Agent CLI TTS Server with TTL-based model unloading",
                        attribution=Attribution(
                            name="agent-cli",
                            url="https://github.com/basnijholt/agent-cli",
                        ),
                        installed=True,
                        version="1.0",
                        voices=voices,
                    ),
                ],
            ).event(),
        )
        return True


async def start_wyoming_server(
    registry: TTSModelRegistry,
    uri: str = "tcp://0.0.0.0:10200",
) -> None:
    """Start the Wyoming TTS server.

    Args:
        registry: Model registry for synthesis.
        uri: URI to bind the server to (e.g., "tcp://0.0.0.0:10200").

    """
    server = AsyncServer.from_uri(uri)
    logger.debug("Wyoming TTS server listening on %s", uri)

    # Create handler factory with registry
    handler_factory = partial(WyomingTTSHandler, registry)

    await server.run(handler_factory)
