"""Wyoming protocol handler for TTS server."""

from __future__ import annotations

import logging
from functools import partial
from typing import TYPE_CHECKING

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import Synthesize

if TYPE_CHECKING:
    from wyoming.event import Event

    from agent_cli.server.tts.model_registry import TTSModelRegistry

logger = logging.getLogger(__name__)

# WAV header size in bytes (standard 44-byte header)
WAV_HEADER_SIZE = 44


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
                    rate=22050,
                    width=2,
                    channels=1,
                ).event(),
            )
            await self.write_event(AudioStop().event())
            return False

        try:
            manager = self._registry.get_manager()
            result = await manager.synthesize(
                text,
                voice=synthesize.voice,
                speed=1.0,
            )

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
                result.audio[WAV_HEADER_SIZE:]
                if len(result.audio) > WAV_HEADER_SIZE
                else result.audio
            )

            # Send in chunks for streaming
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

            # Send audio stop
            await self.write_event(AudioStop().event())

            logger.info(
                "Wyoming synthesis: %d chars -> %.1fs audio",
                len(text),
                result.duration,
            )

        except Exception:
            logger.exception("Wyoming synthesis failed")
            # Send empty audio on error
            await self.write_event(
                AudioStart(
                    rate=22050,
                    width=2,
                    channels=1,
                ).event(),
            )
            await self.write_event(AudioStop().event())

        return False

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
                languages=["en"],  # Piper models are typically language-specific
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
    uri: str = "tcp://0.0.0.0:10400",
) -> None:
    """Start the Wyoming TTS server.

    Args:
        registry: Model registry for synthesis.
        uri: URI to bind the server to (e.g., "tcp://0.0.0.0:10400").

    """
    server = AsyncServer.from_uri(uri)
    logger.debug("Wyoming TTS server listening on %s", uri)

    # Create handler factory with registry
    handler_factory = partial(WyomingTTSHandler, registry)

    await server.run(handler_factory)
