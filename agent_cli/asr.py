"""Module for Automatic Speech Recognition using Wyoming or OpenAI."""

from __future__ import annotations

import asyncio
import io
from functools import partial
from typing import TYPE_CHECKING

from wyoming.asr import Transcribe, Transcript, TranscriptChunk, TranscriptStart, TranscriptStop
from wyoming.audio import AudioChunk, AudioStart, AudioStop

from agent_cli import constants
from agent_cli.audio import (
    open_pyaudio_stream,
    read_audio_stream,
    read_from_queue,
    setup_input_stream,
)

from agent_cli.core.audio import (
    open_pyaudio_stream,
    read_audio_stream,
    read_from_queue,
    setup_input_stream,
)
from agent_cli.services.factory import get_asr_service
from agent_cli.services.local import (
    WyomingTranscriptionService,
    manage_send_receive_tasks,
    wyoming_client_context,
)
from agent_cli.services.openai import OpenAITranscriptionService

if TYPE_CHECKING:
    import logging
    from collections.abc import Awaitable, Callable

    import pyaudio
    from rich.live import Live
    from wyoming.client import AsyncClient

    from agent_cli import config
    from agent_cli.core.utils import InteractiveStopEvent


def get_transcriber(
    provider_config: config.ProviderSelection,
    audio_input_config: config.AudioInput,
    wyoming_asr_config: config.WyomingASR,
    openai_asr_config: config.OpenAIASR,
    openai_llm_config: config.OpenAILLM,
    logger: logging.Logger,
    *,
    quiet: bool = False,
) -> Callable[..., Awaitable[str | None]]:
    """Return the appropriate transcriber for live audio based on the provider."""
    asr_service = get_asr_service(
        provider_config,
        wyoming_asr_config,
        openai_asr_config,
        openai_llm_config,
        logger,
        quiet=quiet,
    )

    async def transcribe_live_audio(p: pyaudio.PyAudio, stop_event: InteractiveStopEvent, live: Live) -> str | None:
        """Record and transcribe live audio."""
        audio_data = await record_audio_with_manual_stop(
            p,
            audio_input_config.input_device_index,
            stop_event,
            logger,
            quiet=quiet,
            live=live,
        )
        if not audio_data:
            return None
        return await asr_service.transcribe(audio_data)

    return transcribe_live_audio


def get_recorded_audio_transcriber(
    provider_config: config.ProviderSelection,
    wyoming_asr_config: config.WyomingASR,
    openai_asr_config: config.OpenAIASR,
    openai_llm_config: config.OpenAILLM,
    logger: logging.Logger,
    *,
    quiet: bool = False,
) -> Callable[[bytes], Awaitable[str]]:
    """Return the appropriate transcriber for recorded audio based on the provider."""
    asr_service = get_asr_service(
        provider_config,
        wyoming_asr_config,
        openai_asr_config,
        openai_llm_config,
        logger,
        quiet=quiet,
    )
    return asr_service.transcribe


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
    await client.write_event(AudioStart(**constants.WYOMING_AUDIO_CONFIG).event())

    async def send_chunk(chunk: bytes) -> None:
        """Send audio chunk to ASR server."""
        await client.write_event(AudioChunk(audio=chunk, **constants.WYOMING_AUDIO_CONFIG).event())

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


async def record_audio_to_buffer(
    queue: asyncio.Queue,
    logger: logging.Logger,
) -> bytes:
    """Record audio from a queue to a buffer."""
    audio_buffer = io.BytesIO()

    def buffer_chunk(chunk: bytes) -> None:
        """Buffer audio chunk."""
        audio_buffer.write(chunk)

    await read_from_queue(queue=queue, chunk_handler=buffer_chunk, logger=logger)

    return audio_buffer.getvalue()


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


async def transcribe_recorded_audio_wyoming(
    *,
    audio_data: bytes,
    wyoming_asr_config: config.WyomingASR,
    logger: logging.Logger,
    quiet: bool = False,
    **_kwargs: object,
) -> str:
    """Process pre-recorded audio data with Wyoming ASR server."""
    service = WyomingTranscriptionService(wyoming_asr_config, logger, quiet=quiet)
    return await service.transcribe(audio_data)


async def transcribe_live_audio_wyoming(
    *,
    audio_input_config: config.AudioInput,
    wyoming_asr_config: config.WyomingASR,
    logger: logging.Logger,
    p: pyaudio.PyAudio,
    stop_event: InteractiveStopEvent,
    live: Live,
    quiet: bool = False,
    chunk_callback: Callable[[str], None] | None = None,
    final_callback: Callable[[str], None] | None = None,
    **_kwargs: object,
) -> str | None:
    """Unified ASR transcription function."""
    service = WyomingTranscriptionService(wyoming_asr_config, logger, quiet=quiet)
    audio_data = await record_audio_with_manual_stop(
        p,
        audio_input_config.input_device_index,
        stop_event,
        logger,
        quiet=quiet,
        live=live,
    )
    if not audio_data:
        return None
    transcript = await service.transcribe(audio_data)
    if chunk_callback:
        chunk_callback(transcript)
    if final_callback:
        final_callback(transcript)
    return transcript


async def transcribe_live_audio_openai(
    *,
    audio_input_config: config.AudioInput,
    openai_asr_config: config.OpenAIASR,
    openai_llm_config: config.OpenAILLM,
    logger: logging.Logger,
    p: pyaudio.PyAudio,
    stop_event: InteractiveStopEvent,
    live: Live,
    quiet: bool = False,
    **_kwargs: object,
) -> str | None:
    """Record and transcribe live audio using OpenAI Whisper."""
    service = OpenAITranscriptionService(openai_asr_config, openai_llm_config, logger)
    audio_data = await record_audio_with_manual_stop(
        p,
        audio_input_config.input_device_index,
        stop_event,
        logger,
        quiet=quiet,
        live=live,
    )
    if not audio_data:
        return None
    return await service.transcribe(audio_data)
