"""Module for Wake Word Detection using Wyoming."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING

from agent_cli import config, constants
from agent_cli.core.audio import read_from_queue
from agent_cli.core.utils import manage_send_receive_tasks
from agent_cli.services._wyoming_utils import wyoming_client_context

if TYPE_CHECKING:
    import logging
    from collections.abc import Awaitable, Callable

    from rich.live import Live
    from wyoming.client import AsyncClient


def create_wake_word_detector(
    wake_word_cfg: config.WakeWord,
) -> Callable[..., Awaitable[str | None]]:
    """Return a wake word detector function."""
    return partial(_detect_wake_word_from_queue, wake_word_cfg=wake_word_cfg)


async def _send_audio_from_queue_for_wake_detection(
    client: AsyncClient,
    queue: asyncio.Queue,
    logger: logging.Logger,
    live: Live | None,
    quiet: bool,
    progress_message: str,
) -> None:
    """Read from a queue and send to Wyoming wake word server."""
    from wyoming.audio import AudioChunk, AudioStart, AudioStop  # noqa: PLC0415

    await client.write_event(AudioStart(**constants.WYOMING_AUDIO_CONFIG).event())
    seconds_streamed = 0.0

    async def send_chunk(chunk: bytes) -> None:
        nonlocal seconds_streamed
        """Send audio chunk to wake word server."""
        await client.write_event(
            AudioChunk(audio=chunk, **constants.WYOMING_AUDIO_CONFIG).event(),
        )
        seconds_streamed += len(chunk) / (constants.AUDIO_RATE * constants.AUDIO_CHANNELS * 2)
        if live and not quiet:
            live.update(f"{progress_message}... ({seconds_streamed:.1f}s)")

    try:
        await read_from_queue(queue=queue, chunk_handler=send_chunk, logger=logger)
    finally:
        if client._writer is not None:
            await client.write_event(AudioStop().event())
            logger.debug("Sent AudioStop for wake detection")


async def _receive_wake_detection(
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
    from wyoming.wake import Detection, NotDetected  # noqa: PLC0415

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


async def _detect_wake_word_from_queue(
    wake_word_cfg: config.WakeWord,
    logger: logging.Logger,
    queue: asyncio.Queue,
    *,
    live: Live | None = None,
    detection_callback: Callable[[str], None] | None = None,
    quiet: bool = False,
    progress_message: str = "Listening for wake word",
) -> str | None:
    """Detect wake word from an audio queue."""
    from wyoming.wake import Detect  # noqa: PLC0415

    try:
        async with wyoming_client_context(
            wake_word_cfg.wake_server_ip,
            wake_word_cfg.wake_server_port,
            "wake word",
            logger,
            quiet=quiet,
        ) as client:
            await client.write_event(Detect(names=[wake_word_cfg.wake_word]).event())

            _send_task, recv_task = await manage_send_receive_tasks(
                _send_audio_from_queue_for_wake_detection(
                    client,
                    queue,
                    logger,
                    live,
                    quiet,
                    progress_message,
                ),
                _receive_wake_detection(client, logger, detection_callback=detection_callback),
                return_when=asyncio.FIRST_COMPLETED,
            )

            if recv_task.done() and not recv_task.cancelled():
                return recv_task.result()

            return None
    except (ConnectionRefusedError, asyncio.CancelledError, Exception):
        return None
