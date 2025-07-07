"""Module for Wake Word Detection using Wyoming."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.wake import Detect, Detection, NotDetected

from agent_cli import config
from agent_cli.audio import read_audio_stream, read_from_queue
from agent_cli.wyoming_utils import manage_send_receive_tasks, wyoming_client_context

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

    import pyaudio
    from rich.live import Live
    from wyoming.client import AsyncClient

    from agent_cli.utils import InteractiveStopEvent


async def _send_audio_for_wake_detection(
    client: AsyncClient,
    stream: pyaudio.Stream,
    stop_event: InteractiveStopEvent,
    logger: logging.Logger,
    *,
    live: Live,
    quiet: bool = False,
    progress_message: str = "Listening for wake word",
) -> None:
    """Read from mic and send to Wyoming wake word server.

    Args:
        client: Wyoming client connection
        stream: PyAudio stream
        stop_event: Event to stop recording
        logger: Logger instance
        live: Rich Live display for progress
        quiet: If True, suppress all console output
        progress_message: Message to display during listening

    """
    await client.write_event(AudioStart(**config.WYOMING_AUDIO_CONFIG).event())

    async def send_chunk(chunk: bytes) -> None:
        """Send audio chunk to wake word server."""
        await client.write_event(
            AudioChunk(audio=chunk, **config.WYOMING_AUDIO_CONFIG).event(),
        )

    try:
        # Use common audio reading function
        await read_audio_stream(
            stream=stream,
            stop_event=stop_event,
            chunk_handler=send_chunk,
            logger=logger,
            live=live,
            quiet=quiet,
            progress_message=progress_message,
            progress_style="blue",
        )
    finally:
        if client._writer is not None:
            await client.write_event(AudioStop().event())
            logger.debug("Sent AudioStop for wake detection")


async def _send_audio_from_queue_for_wake_detection(
    client: AsyncClient,
    queue: asyncio.Queue,
    logger: logging.Logger,
    live: Live | None,
    quiet: bool,
    progress_message: str,
) -> None:
    """Read from a queue and send to Wyoming wake word server."""
    await client.write_event(AudioStart(**config.WYOMING_AUDIO_CONFIG).event())
    seconds_streamed = 0.0

    async def send_chunk(chunk: bytes) -> None:
        nonlocal seconds_streamed
        """Send audio chunk to wake word server."""
        await client.write_event(
            AudioChunk(audio=chunk, **config.WYOMING_AUDIO_CONFIG).event(),
        )
        seconds_streamed += len(chunk) / (config.PYAUDIO_RATE * config.PYAUDIO_CHANNELS * 2)
        if live and not quiet:
            live.update(f"{progress_message}... ({seconds_streamed:.1f}s)")

    try:
        await read_from_queue(
            queue=queue,
            chunk_handler=send_chunk,
            logger=logger,
        )
    finally:
        if client._writer is not None:
            await client.write_event(AudioStop().event())
            logger.debug("Sent AudioStop for wake detection")


async def receive_wake_detection(
    client: AsyncClient,
    logger: logging.Logger,
    *,
    detection_callback: Callable[[str], None] | None = None,
) -> str | None:
    """Receive wake word detection events.

    Args:
        client: Wyoming client connection
        logger: Logger instance
        detection_callback: Optional callback for when wake word is detected

    Returns:
        Name of detected wake word or None if no detection

    """
    while True:
        event = await client.read_event()
        if event is None:
            logger.warning("Connection to wake word server lost.")
            break

        if Detection.is_type(event.type):
            detection = Detection.from_event(event)
            wake_word_name = detection.name or "unknown"
            logger.info("Wake word detected: %s", wake_word_name)
            if detection_callback:
                detection_callback(wake_word_name)
            return wake_word_name
        if NotDetected.is_type(event.type):
            logger.debug("No wake word detected")
            break
        logger.debug("Ignoring event type: %s", event.type)

    return None


async def detect_wake_word(
    wake_server_ip: str,
    wake_server_port: int,
    wake_word_name: str,
    logger: logging.Logger,
    stream: pyaudio.Stream,
    stop_event: InteractiveStopEvent,
    *,
    live: Live,
    quiet: bool = False,
    detection_callback: Callable[[str], None] | None = None,
    progress_message: str = "Listening for wake word",
) -> str | None:
    """Detect wake word in audio stream.

    Args:
        wake_server_ip: Wyoming wake word server IP
        wake_server_port: Wyoming wake word server port
        wake_word_name: Name of wake word to detect
        logger: Logger instance
        stream: PyAudio stream to use
        stop_event: Event to stop recording
        live: Rich Live display for progress
        quiet: If True, suppress all console output
        detection_callback: Callback when wake word is detected
        progress_message: Message to display during listening

    Returns:
        Name of detected wake word or None if error/no detection

    """
    try:
        async with wyoming_client_context(
            wake_server_ip,
            wake_server_port,
            "wake word",
            logger,
            quiet=quiet,
        ) as client:
            # Send detect request with specific wake word
            await client.write_event(Detect(names=[wake_word_name]).event())

            _send_task, recv_task = await manage_send_receive_tasks(
                _send_audio_for_wake_detection(
                    client,
                    stream,
                    stop_event,
                    logger,
                    live=live,
                    quiet=quiet,
                    progress_message=progress_message,
                ),
                receive_wake_detection(client, logger, detection_callback=detection_callback),
                return_when=asyncio.FIRST_COMPLETED,
            )

            # If recv_task completed first, it means we detected a wake word
            if recv_task.done() and not recv_task.cancelled():
                return recv_task.result()

            return None
    except (ConnectionRefusedError, asyncio.CancelledError, Exception):
        return None


async def detect_wake_word_from_queue(
    wake_server_ip: str,
    wake_server_port: int,
    wake_word_name: str,
    logger: logging.Logger,
    queue: asyncio.Queue,
    *,
    live: Live | None = None,
    detection_callback: Callable[[str], None] | None = None,
    quiet: bool = False,
    progress_message: str = "Listening for wake word",
) -> str | None:
    """Detect wake word from an audio queue."""
    try:
        async with wyoming_client_context(
            wake_server_ip,
            wake_server_port,
            "wake word",
            logger,
            quiet=quiet,
        ) as client:
            await client.write_event(Detect(names=[wake_word_name]).event())

            _send_task, recv_task = await manage_send_receive_tasks(
                _send_audio_from_queue_for_wake_detection(
                    client,
                    queue,
                    logger,
                    live,
                    quiet,
                    progress_message,
                ),
                receive_wake_detection(client, logger, detection_callback=detection_callback),
                return_when=asyncio.FIRST_COMPLETED,
            )

            if recv_task.done() and not recv_task.cancelled():
                return recv_task.result()

            return None
    except (ConnectionRefusedError, asyncio.CancelledError, Exception):
        return None
