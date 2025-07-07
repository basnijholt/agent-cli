"""Module for Automatic Speech Recognition using Wyoming."""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING

from wyoming.asr import Transcribe, Transcript, TranscriptChunk, TranscriptStart, TranscriptStop
from wyoming.audio import AudioChunk, AudioStart, AudioStop

from agent_cli import config
from agent_cli.audio import (
    open_pyaudio_stream,
    read_audio_stream,
    read_from_queue,
    setup_input_stream,
)
from agent_cli.utils import print_with_style
from agent_cli.wyoming_utils import manage_send_receive_tasks, wyoming_client_context

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

    import pyaudio
    from rich.live import Live
    from wyoming.client import AsyncClient

    from agent_cli.utils import InteractiveStopEvent


async def _send_audio(
    client: AsyncClient,
    stream: pyaudio.Stream,
    stop_event: InteractiveStopEvent,
    logger: logging.Logger,
    *,
    live: Live,
    quiet: bool = False,
) -> None:
    """Read from mic and send to Wyoming server."""
    await client.write_event(Transcribe().event())
    await client.write_event(AudioStart(**config.WYOMING_AUDIO_CONFIG).event())

    async def send_chunk(chunk: bytes) -> None:
        """Send audio chunk to ASR server."""
        await client.write_event(
            AudioChunk(audio=chunk, **config.WYOMING_AUDIO_CONFIG).event(),
        )

    try:
        await read_audio_stream(
            stream=stream,
            stop_event=stop_event,
            chunk_handler=send_chunk,
            logger=logger,
            live=live,
            quiet=quiet,
            progress_message="Listening",
            progress_style="blue",
        )
    finally:
        await client.write_event(AudioStop().event())
        logger.debug("Sent AudioStop")


async def _send_audio_from_queue(
    client: AsyncClient,
    queue: asyncio.Queue,
    logger: logging.Logger,
) -> None:
    """Read from a queue and send to Wyoming server."""
    await client.write_event(Transcribe().event())
    await client.write_event(AudioStart(**config.WYOMING_AUDIO_CONFIG).event())

    async def send_chunk(chunk: bytes) -> None:
        """Send audio chunk to ASR server."""
        await client.write_event(
            AudioChunk(audio=chunk, **config.WYOMING_AUDIO_CONFIG).event(),
        )

    try:
        await read_from_queue(
            queue=queue,
            chunk_handler=send_chunk,
            logger=logger,
        )
    finally:
        await client.write_event(AudioStop().event())
        logger.debug("Sent AudioStop")


async def record_audio_to_buffer(
    queue: asyncio.Queue,
    logger: logging.Logger,
) -> bytes:
    """Record audio from a queue to a buffer."""
    audio_buffer = io.BytesIO()

    def buffer_chunk(chunk: bytes) -> None:
        """Buffer audio chunk."""
        audio_buffer.write(chunk)

    await read_from_queue(
        queue=queue,
        chunk_handler=buffer_chunk,
        logger=logger,
    )

    return audio_buffer.getvalue()


async def receive_transcript(
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
        elif TranscriptStart.is_type(event.type) or TranscriptStop.is_type(event.type):
            logger.debug("Received %s", event.type)
        else:
            logger.debug("Ignoring event type: %s", event.type)

    return transcript_text


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
    if not quiet:
        print_with_style("🎤 Recording... Press hotkey to stop", style="green")

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


async def transcribe_recorded_audio(
    audio_data: bytes,
    asr_server_ip: str,
    asr_server_port: int,
    logger: logging.Logger,
    quiet: bool = False,
) -> str:
    """Process pre-recorded audio data with Wyoming ASR server."""
    try:
        async with wyoming_client_context(
            asr_server_ip,
            asr_server_port,
            "ASR",
            logger,
            quiet=quiet,
        ) as client:
            await client.write_event(Transcribe().event())
            await client.write_event(AudioStart(**config.WYOMING_AUDIO_CONFIG).event())

            chunk_size = config.PYAUDIO_CHUNK_SIZE * 2
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i : i + chunk_size]
                await client.write_event(
                    AudioChunk(audio=chunk, **config.WYOMING_AUDIO_CONFIG).event(),
                )
                logger.debug("Sent %d byte(s) of audio", len(chunk))

            await client.write_event(AudioStop().event())
            logger.debug("Sent AudioStop")

            return await receive_transcript(client, logger)
    except (ConnectionRefusedError, Exception):
        return ""


async def transcribe_live_audio(
    asr_server_ip: str,
    asr_server_port: int,
    input_device_index: int | None,
    logger: logging.Logger,
    p: pyaudio.PyAudio,
    stop_event: InteractiveStopEvent,
    *,
    live: Live,
    quiet: bool = False,
    chunk_callback: Callable[[str], None] | None = None,
    final_callback: Callable[[str], None] | None = None,
) -> str | None:
    """Unified ASR transcription function."""
    try:
        async with wyoming_client_context(
            asr_server_ip,
            asr_server_port,
            "ASR",
            logger,
            quiet=quiet,
        ) as client:
            stream_config = setup_input_stream(input_device_index)
            with open_pyaudio_stream(p, **stream_config) as stream:
                _, recv_task = await manage_send_receive_tasks(
                    _send_audio(client, stream, stop_event, logger, live=live, quiet=quiet),
                    receive_transcript(
                        client,
                        logger,
                        chunk_callback=chunk_callback,
                        final_callback=final_callback,
                    ),
                    return_when=asyncio.ALL_COMPLETED,
                )
                return recv_task.result()
    except (ConnectionRefusedError, Exception):
        return None
