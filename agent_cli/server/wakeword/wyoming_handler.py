"""Wyoming protocol handler for wakeword server."""

from __future__ import annotations

import logging
from functools import partial
from typing import TYPE_CHECKING

from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStart, AudioStop
from wyoming.info import Attribution, Describe, Info, WakeModel, WakeProgram
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.wake import Detect, Detection, NotDetected

if TYPE_CHECKING:
    from wyoming.event import Event

    from agent_cli.server.wakeword.model_registry import WakewordModelRegistry

logger = logging.getLogger(__name__)

# Wakeword detection uses 16kHz, 16-bit mono audio
WAKEWORD_RATE = 16000
WAKEWORD_WIDTH = 2
WAKEWORD_CHANNELS = 1


class WyomingWakewordHandler(AsyncEventHandler):
    """Wyoming event handler for wakeword detection.

    Handles the Wyoming protocol for wake word detection:
    - Receives audio chunks
    - Processes audio for wake word detection
    - Returns Detection events when wake words are detected
    """

    def __init__(
        self,
        registry: WakewordModelRegistry,
        *args: object,
        **kwargs: object,
    ) -> None:
        """Initialize the handler.

        Args:
            registry: Model registry for getting wakeword models.
            *args: Passed to parent class.
            **kwargs: Passed to parent class.

        """
        super().__init__(*args, **kwargs)
        self._registry = registry
        self._audio_converter = AudioChunkConverter(
            rate=WAKEWORD_RATE,
            width=WAKEWORD_WIDTH,
            channels=WAKEWORD_CHANNELS,
        )
        self._is_detecting = False
        self._model_name: str | None = None

    async def handle_event(self, event: Event) -> bool:
        """Handle a Wyoming event.

        Args:
            event: The event to handle.

        Returns:
            True to continue processing events, False to stop.

        """
        if Describe.is_type(event.type):
            return await self._handle_describe()

        if Detect.is_type(event.type):
            return await self._handle_detect(event)

        if AudioStart.is_type(event.type):
            return await self._handle_audio_start()

        if AudioChunk.is_type(event.type):
            return await self._handle_audio_chunk(event)

        if AudioStop.is_type(event.type):
            return await self._handle_audio_stop()

        return True

    async def _handle_describe(self) -> bool:
        """Handle describe event - return server capabilities."""
        logger.debug("Describe event")

        # Get list of available models from all registered managers
        models: list[WakeModel] = []
        seen_models: set[str] = set()

        for status in self._registry.list_status():
            manager = self._registry.get_manager(status.name)
            if manager.is_loaded:
                for model_info in manager.get_available_models():
                    if model_info.name not in seen_models:
                        seen_models.add(model_info.name)
                        models.append(
                            WakeModel(
                                name=model_info.name,
                                description=model_info.phrase,
                                phrase=model_info.phrase,
                                attribution=Attribution(
                                    name="dscripka",
                                    url="https://github.com/dscripka/openWakeWord",
                                ),
                                installed=True,
                                languages=model_info.languages,
                                version="v0.1",
                            ),
                        )

        # If no models are loaded, add registered models
        if not models:
            for status in self._registry.list_status():
                if status.name not in seen_models:
                    seen_models.add(status.name)
                    phrase = " ".join(
                        w.capitalize()
                        for w in status.name.replace("_", " ").replace("-", " ").split()
                    )
                    models.append(
                        WakeModel(
                            name=status.name,
                            description=phrase,
                            phrase=phrase,
                            attribution=Attribution(
                                name="dscripka",
                                url="https://github.com/dscripka/openWakeWord",
                            ),
                            installed=True,
                            languages=["en"],
                            version="v0.1",
                        ),
                    )

        await self.write_event(
            Info(
                wake=[
                    WakeProgram(
                        name="agent-cli-wakeword",
                        description="Agent CLI Wakeword Server with TTL-based model unloading",
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

    async def _handle_detect(self, event: Event) -> bool:
        """Handle detect event - configure which wake words to detect."""
        logger.debug("Detect event")
        detect = Detect.from_event(event)

        # Use first requested name or default model
        if detect.names:
            self._model_name = detect.names[0]
        else:
            self._model_name = self._registry.default_model

        logger.debug("Will detect wake word: %s", self._model_name)
        return True

    async def _handle_audio_start(self) -> bool:
        """Handle audio start event - reset detector state."""
        logger.debug("AudioStart")
        self._is_detecting = True

        # Reset the detector for the requested model
        if self._model_name:
            try:
                manager = self._registry.get_manager(self._model_name)
                manager.reset()
            except ValueError:
                logger.warning("Model %s not found", self._model_name)

        return True

    async def _handle_audio_chunk(self, event: Event) -> bool:
        """Handle an audio chunk event - process for wake word detection."""
        if not self._is_detecting:
            return True

        chunk = AudioChunk.from_event(event)
        chunk = self._audio_converter.convert(chunk)

        try:
            manager = self._registry.get_manager(self._model_name)
            detections = await manager.process_audio(chunk.audio)

            for detection in detections:
                await self.write_event(
                    Detection(
                        name=detection.name,
                        timestamp=detection.timestamp,
                    ).event(),
                )
                logger.info(
                    "Wyoming wake word detected: %s at %dms",
                    detection.name,
                    detection.timestamp,
                )

        except ValueError as e:
            logger.warning("Error processing audio: %s", e)

        return True

    async def _handle_audio_stop(self) -> bool:
        """Handle audio stop event - inform client if no detection occurred."""
        logger.debug("AudioStop")

        if self._is_detecting:
            # Check if any detection was made
            # If not, send NotDetected
            try:
                manager = self._registry.get_manager(self._model_name)
                # Check if detected flag is set
                if manager.is_loaded:
                    backend = await manager.get_model()
                    if hasattr(backend, "_detector") and backend._detector:
                        if not backend._detector.is_detected:
                            await self.write_event(NotDetected().event())
                    else:
                        await self.write_event(NotDetected().event())
                else:
                    await self.write_event(NotDetected().event())
            except ValueError:
                await self.write_event(NotDetected().event())

        self._is_detecting = False
        return True


async def start_wyoming_server(
    registry: WakewordModelRegistry,
    uri: str = "tcp://0.0.0.0:10400",
) -> None:
    """Start the Wyoming wakeword server.

    Args:
        registry: Model registry for wakeword detection.
        uri: URI to bind the server to (e.g., "tcp://0.0.0.0:10400").

    """
    server = AsyncServer.from_uri(uri)
    logger.debug("Wyoming wakeword server listening on %s", uri)

    # Create handler factory with registry
    handler_factory = partial(WyomingWakewordHandler, registry)

    await server.run(handler_factory)
