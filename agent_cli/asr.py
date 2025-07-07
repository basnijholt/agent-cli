"""Module for Automatic Speech Recognition using Wyoming."""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING

import openai
from wyoming.asr import Transcribe, Transcript, TranscriptChunk, TranscriptStart, TranscriptStop
from wyoming.audio import AudioChunk, AudioStart, AudioStop

from agent_cli import config
from agent_cli.audio import (
    open_pyaudio_stream,
    read_audio_stream,
    read_from_queue,
    setup_input_stream,
)
from agent_cli.utils import print_error_message, print_with_style
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


async def transcribe_audio_openai(
    audio_data: bytes,
    api_key: str,
    model: str,
    logger: logging.Logger,
    *,
    quiet: bool = False,
) -> str:
    """Transcribe audio using OpenAI's Whisper model."""
    if not quiet:
        print_with_style(f"🎤 Transcribing with {model}...", style="yellow")
    try:
        client = openai.AsyncClient(api_key=api_key)
        audio_file = io.BytesIO(audio_data)
        audio_file.name = "audio.wav"  # OpenAI API requires a file name
        response = await client.audio.transcriptions.create(
            model=model,
            file=audio_file,
        )
        logger.info("Successfully transcribed audio with OpenAI.")
        return response.text
    except Exception as e:
        logger.exception("An error occurred during OpenAI transcription.")
        print_error_message(
            f"An unexpected OpenAI error occurred: {e}",
            "Please check your OpenAI API key and connection.",
        )
        return ""


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
    logger: logging.Logger,
    *,
    asr_provider: str = "wyoming",
    asr_server_ip: str | None = None,
    asr_server_port: int | None = None,
    openai_api_key: str | None = None,
    whisper_model: str = "whisper-1",
    quiet: bool = False,
) -> str:
    """Process pre-recorded audio data with the selected ASR provider."""
    if asr_provider == "openai":
        if not openai_api_key:
            msg = "OpenAI API key must be provided for OpenAI ASR."
            raise ValueError(msg)
        return await transcribe_audio_openai(
            audio_data,
            openai_api_key,
            whisper_model,
            logger,
            quiet=quiet,
        )
    if asr_provider == "wyoming":
        if not asr_server_ip or not asr_server_port:
            raise ValueError("Wyoming server IP and port must be provided.")
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

                return await _receive_transcript(client, logger)
        except (ConnectionRefusedError, Exception):
            return ""
    raise ValueError(f"Unknown ASR provider: {asr_provider}")


async def transcribe_live_audio(
    input_device_index: int | None,
    logger: logging.Logger,
    p: pyaudio.PyAudio,
    stop_event: InteractiveStopEvent,
    *,
    live: Live,
    asr_provider: str = "wyoming",
    asr_server_ip: str | None = None,
    asr_server_port: int | None = None,
    openai_api_key: str | None = None,
    whisper_model: str = "whisper-1",
    quiet: bool = False,
    chunk_callback: Callable[[str], None] | None = None,
    final_callback: Callable[[str], None] | None = None,
) -> str | None:
    """Unified ASR transcription function."""
    if asr_provider == "openai":
        if not openai_api_key:
            msg = "OpenAI API key must be provided for OpenAI ASR."
            raise ValueError(msg)
        audio_data = await record_audio_with_manual_stop(
            p,
            input_device_index,
            stop_event,
            logger,
            quiet=quiet,
            live=live,
        )
        result = await transcribe_audio_openai(
            audio_data,
            openai_api_key,
            whisper_model,
            logger,
            quiet=quiet,
        )
        if final_callback:
            final_callback(result)
        return result

    if asr_provider == "wyoming":
        if not asr_server_ip or not asr_server_port:
            msg = "Wyoming server IP and port must be provided."
            raise ValueError(msg)
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
                        _receive_transcript(
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
    msg = f"Unknown ASR provider: {asr_provider}"
    raise ValueError(msg)
