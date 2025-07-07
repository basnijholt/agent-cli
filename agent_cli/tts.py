"""Module for Text-to-Speech using Wyoming."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import wave
from typing import TYPE_CHECKING

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.tts import Synthesize, SynthesizeVoice

from agent_cli import config
from agent_cli.audio import (
    open_pyaudio_stream,
    pyaudio_context,
    setup_output_stream,
)
from agent_cli.utils import (
    InteractiveStopEvent,
    live_timer,
    print_error_message,
    print_with_style,
)
from agent_cli.wyoming_utils import manage_send_receive_tasks, wyoming_client_context

if TYPE_CHECKING:
    import logging

    from rich.live import Live
    from wyoming.client import AsyncClient

has_audiostretchy = importlib.util.find_spec("audiostretchy") is not None


def _create_synthesis_request(
    text: str,
    *,
    voice_name: str | None = None,
    language: str | None = None,
    speaker: str | None = None,
) -> Synthesize:
    """Create a synthesis request with optional voice parameters."""
    synthesize_event = Synthesize(text=text)

    # Add voice parameters if specified
    if voice_name or language or speaker:
        synthesize_event.voice = SynthesizeVoice(
            name=voice_name,
            language=language,
            speaker=speaker,
        )

    return synthesize_event


async def _process_audio_events(
    client: AsyncClient,
    logger: logging.Logger,
) -> tuple[bytes, int | None, int | None, int | None]:
    """Process audio events from TTS server and return audio data with metadata."""
    audio_data = io.BytesIO()
    sample_rate = None
    sample_width = None
    channels = None

    while True:
        event = await client.read_event()
        if event is None:
            logger.warning("Connection to TTS server lost.")
            break

        if AudioStart.is_type(event.type):
            audio_start = AudioStart.from_event(event)
            sample_rate = audio_start.rate
            sample_width = audio_start.width
            channels = audio_start.channels
            logger.debug(
                "Audio stream started: %dHz, %d channels, %d bytes/sample",
                sample_rate,
                channels,
                sample_width,
            )

        elif AudioChunk.is_type(event.type):
            chunk = AudioChunk.from_event(event)
            audio_data.write(chunk.audio)
            logger.debug("Received %d bytes of audio", len(chunk.audio))

        elif AudioStop.is_type(event.type):
            logger.debug("Audio stream completed")
            break
        else:
            logger.debug("Ignoring event type: %s", event.type)

    return audio_data.getvalue(), sample_rate, sample_width, channels


def _create_wav_data(
    audio_data: bytes,
    sample_rate: int,
    sample_width: int,
    channels: int,
) -> bytes:
    """Convert raw audio data to WAV format."""
    wav_data = io.BytesIO()
    with wave.open(wav_data, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data)
    return wav_data.getvalue()


async def _synthesize_speech(
    text: str,
    tts_server_ip: str,
    tts_server_port: int,
    logger: logging.Logger,
    *,
    voice_name: str | None = None,
    language: str | None = None,
    speaker: str | None = None,
    quiet: bool = False,
    live: Live,
) -> bytes | None:
    """Synthesize speech from text using Wyoming TTS server.

    Args:
        text: Text to synthesize
        tts_server_ip: Wyoming TTS server IP
        tts_server_port: Wyoming TTS server port
        logger: Logger instance
        voice_name: Optional voice name
        language: Optional language
        speaker: Optional speaker name
        quiet: If true, suppress console messages
        live: Live instance for timer display

    Returns:
        WAV audio data as bytes, or None if error

    """
    try:
        async with wyoming_client_context(
            tts_server_ip,
            tts_server_port,
            "TTS",
            logger,
            quiet=quiet,
        ) as client:
            # Use live_timer with the provided Live instance
            async with live_timer(live, "🔊 Synthesizing text", style="blue", quiet=quiet):
                # Create and send synthesis request
                synthesize_event = _create_synthesis_request(
                    text,
                    voice_name=voice_name,
                    language=language,
                    speaker=speaker,
                )

                # Process audio events
                _send_task, recv_task = await manage_send_receive_tasks(
                    client.write_event(synthesize_event.event()),
                    _process_audio_events(client, logger),
                )
                audio_data, sample_rate, sample_width, channels = recv_task.result()

            # Convert to WAV format if we have valid audio data and metadata
            if sample_rate and sample_width and channels and audio_data:
                wav_data = _create_wav_data(audio_data, sample_rate, sample_width, channels)
                logger.info("Speech synthesis completed: %d bytes", len(wav_data))
                return wav_data

            logger.warning("No audio data received from TTS server")
            return None
    except (ConnectionRefusedError, Exception):
        return None


def _apply_speed_adjustment(
    audio_data: io.BytesIO,
    speed: float,
) -> tuple[io.BytesIO, bool]:
    """Apply speed adjustment to audio data using AudioStretchy or sample rate fallback.

    Args:
        audio_data: WAV audio data as BytesIO
        speed: Speed multiplier (1.0 = normal, 2.0 = 2x speed, 0.5 = half speed)

    Returns:
        Tuple of (speed-adjusted WAV audio data as BytesIO, bool indicating if speed was changed)

    """
    if speed == 1.0 or not has_audiostretchy:
        return audio_data, False

    # Try AudioStretchy first (high-quality pitch-preserving method)
    from audiostretchy.stretch import AudioStretch  # noqa: PLC0415

    # AudioStretchy closes the input BytesIO during open_wav, so make a copy
    audio_data.seek(0)
    input_copy = io.BytesIO(audio_data.read())

    # Use AudioStretchy for high-quality time stretching
    audio_stretch = AudioStretch()
    audio_stretch.open(file=input_copy, format="wav")
    audio_stretch.stretch(ratio=1 / speed)

    # Save to output BytesIO with close=False to keep it open
    out = io.BytesIO()
    audio_stretch.save_wav(out, close=False)
    out.seek(0)  # Reset position for reading
    return out, True


async def play_audio(
    audio_data: bytes,
    logger: logging.Logger,
    *,
    output_device_index: int | None = None,
    quiet: bool = False,
    stop_event: InteractiveStopEvent | None = None,
    speed: float = 1.0,
    live: Live,
) -> None:
    """Play WAV audio data using PyAudio with proper resource management.

    Args:
        audio_data: WAV audio data as bytes
        logger: Logger instance
        output_device_index: Optional output device index
        quiet: If true, suppress console messages
        stop_event: Optional stop event to interrupt playback
        speed: Speed multiplier (1.0 = normal, 2.0 = 2x speed, 0.5 = half speed)
        live: Live instance for timer display

    """
    try:
        # Apply high-quality speed adjustment if possible
        wav_io = io.BytesIO(audio_data)
        wav_io, speed_changed = _apply_speed_adjustment(wav_io, speed)

        # Parse WAV file
        with wave.open(wav_io, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frames = wav_file.readframes(wav_file.getnframes())

        # Calculate effective sample rate for fallback method
        if not speed_changed:
            sample_rate = int(sample_rate * speed)

        # Determine message
        base_msg = f"🔊 Playing audio at {speed}x speed" if speed != 1.0 else "🔊 Playing audio"

        # Use live_timer with the provided Live instance
        async with live_timer(live, base_msg, style="blue", quiet=quiet):
            with pyaudio_context() as p:
                stream_config = setup_output_stream(
                    output_device_index,
                    sample_rate=sample_rate,
                    sample_width=sample_width,
                    channels=channels,
                )
                with open_pyaudio_stream(p, **stream_config) as stream:
                    # Play in chunks to avoid blocking
                    chunk_size = config.PYAUDIO_CHUNK_SIZE
                    for i in range(0, len(frames), chunk_size):
                        # Check for interruption
                        if stop_event and stop_event.is_set():
                            logger.info("Audio playback interrupted")
                            if not quiet:
                                print_with_style("⏹️ Audio playback interrupted", style="yellow")
                            break
                        chunk = frames[i : i + chunk_size]
                        stream.write(chunk)

                        # Yield control to the event loop so signal handlers can run
                        await asyncio.sleep(0)

        if not (stop_event and stop_event.is_set()):
            logger.info("Audio playback completed (speed: %.1fx)", speed)
            if not quiet:
                print_with_style("✅ Audio playback finished")

    except Exception as e:
        logger.exception("Error during audio playback")
        if not quiet:
            print_error_message(f"Playback error: {e}")


async def speak_text(
    text: str,
    tts_server_ip: str,
    tts_server_port: int,
    logger: logging.Logger,
    *,
    voice_name: str | None = None,
    language: str | None = None,
    speaker: str | None = None,
    output_device_index: int | None = None,
    quiet: bool = False,
    play_audio_flag: bool = True,
    stop_event: InteractiveStopEvent | None = None,
    speed: float = 1.0,
    live: Live,
) -> bytes | None:
    """Synthesize and optionally play speech from text.

    Args:
        text: Text to synthesize and speak
        tts_server_ip: Wyoming TTS server IP
        tts_server_port: Wyoming TTS server port
        logger: Logger instance
        voice_name: Optional voice name
        language: Optional language
        speaker: Optional speaker name
        output_device_index: Optional output device index
        quiet: If true, suppress console messages
        play_audio_flag: Whether to play the audio immediately
        stop_event: Optional stop event to interrupt playback
        speed: Speed multiplier (1.0 = normal, 2.0 = 2x speed, 0.5 = half speed)
        live: Live instance for timer display

    Returns:
        WAV audio data as bytes, or None if error

    """
    # Synthesize speech
    audio_data = await _synthesize_speech(
        text=text,
        tts_server_ip=tts_server_ip,
        tts_server_port=tts_server_port,
        logger=logger,
        voice_name=voice_name,
        language=language,
        speaker=speaker,
        quiet=quiet,
        live=live,
    )

    # Play audio if requested and synthesis succeeded
    if audio_data and play_audio_flag:
        await play_audio(
            audio_data,
            logger,
            output_device_index=output_device_index,
            quiet=quiet,
            stop_event=stop_event,
            speed=speed,
            live=live,
        )

    return audio_data
