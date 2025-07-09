"""Module for Text-to-Speech using Wyoming or OpenAI."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import wave
from functools import partial
from typing import TYPE_CHECKING

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.tts import Synthesize, SynthesizeVoice

from agent_cli import constants
from agent_cli.audio import open_pyaudio_stream, pyaudio_context, setup_output_stream
from agent_cli.services import synthesize_speech_openai
from agent_cli.utils import InteractiveStopEvent, live_timer, print_error_message, print_with_style
from agent_cli.wyoming_utils import manage_send_receive_tasks, wyoming_client_context

if TYPE_CHECKING:
    import logging
    from collections.abc import Awaitable, Callable

    from rich.live import Live
    from wyoming.client import AsyncClient

    from agent_cli.agents import config

has_audiostretchy = importlib.util.find_spec("audiostretchy") is not None


def get_synthesizer(
    provider_config: config.ProviderSelection,
    audio_output_config: config.AudioOutput,
    wyoming_tts_config: config.WyomingTTS,
    openai_tts_config: config.OpenAITTS,
    openai_llm_config: config.OpenAILLM,
) -> Callable[..., Awaitable[bytes | None]]:
    """Return the appropriate synthesizer based on the config."""
    if not audio_output_config.enable_tts:
        return _dummy_synthesizer
    if provider_config.tts_provider == "openai":
        return partial(
            _synthesize_speech_openai,
            openai_tts_config=openai_tts_config,
            openai_llm_config=openai_llm_config,
        )
    return partial(_synthesize_speech_wyoming, wyoming_tts_config=wyoming_tts_config)


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


async def _dummy_synthesizer(**_kwargs: object) -> bytes | None:
    """A dummy synthesizer that does nothing."""
    return None


async def _synthesize_speech_openai(
    *,
    text: str,
    openai_tts_config: config.OpenAITTS,
    openai_llm_config: config.OpenAILLM,
    logger: logging.Logger,
    **_kwargs: object,
) -> bytes | None:
    """Synthesize speech from text using OpenAI TTS server."""
    return await synthesize_speech_openai(
        text=text,
        openai_tts_config=openai_tts_config,
        openai_llm_config=openai_llm_config,
        logger=logger,
    )


async def _synthesize_speech_wyoming(
    *,
    text: str,
    wyoming_tts_config: config.WyomingTTS,
    logger: logging.Logger,
    quiet: bool = False,
    live: Live,
    **_kwargs: object,
) -> bytes | None:
    """Synthesize speech from text using Wyoming TTS server."""
    try:
        async with wyoming_client_context(
            wyoming_tts_config.wyoming_tts_ip,
            wyoming_tts_config.wyoming_tts_port,
            "TTS",
            logger,
            quiet=quiet,
        ) as client:
            async with live_timer(live, "🔊 Synthesizing text", style="blue", quiet=quiet):
                synthesize_event = _create_synthesis_request(
                    text,
                    voice_name=wyoming_tts_config.wyoming_voice,
                    language=wyoming_tts_config.wyoming_tts_language,
                    speaker=wyoming_tts_config.wyoming_speaker,
                )
                _send_task, recv_task = await manage_send_receive_tasks(
                    client.write_event(synthesize_event.event()),
                    _process_audio_events(client, logger),
                )
                audio_data, sample_rate, sample_width, channels = recv_task.result()
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
    """Apply speed adjustment to audio data."""
    if speed == 1.0 or not has_audiostretchy:
        return audio_data, False
    from audiostretchy.stretch import AudioStretch  # noqa: PLC0415

    audio_data.seek(0)
    input_copy = io.BytesIO(audio_data.read())
    audio_stretch = AudioStretch()
    audio_stretch.open(file=input_copy, format="wav")
    audio_stretch.stretch(ratio=1 / speed)
    out = io.BytesIO()
    audio_stretch.save_wav(out, close=False)
    out.seek(0)
    return out, True


async def play_audio(
    audio_data: bytes,
    logger: logging.Logger,
    *,
    audio_output_config: config.AudioOutput,
    quiet: bool = False,
    stop_event: InteractiveStopEvent | None = None,
    live: Live,
) -> None:
    """Play WAV audio data using PyAudio."""
    try:
        wav_io = io.BytesIO(audio_data)
        speed = audio_output_config.tts_speed
        wav_io, speed_changed = _apply_speed_adjustment(wav_io, speed)
        with wave.open(wav_io, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frames = wav_file.readframes(wav_file.getnframes())
        if not speed_changed:
            sample_rate = int(sample_rate * speed)
        base_msg = f"🔊 Playing audio at {speed}x speed" if speed != 1.0 else "🔊 Playing audio"
        async with live_timer(live, base_msg, style="blue", quiet=quiet):
            with pyaudio_context() as p:
                stream_config = setup_output_stream(
                    audio_output_config.output_device_index,
                    sample_rate=sample_rate,
                    sample_width=sample_width,
                    channels=channels,
                )
                with open_pyaudio_stream(p, **stream_config) as stream:
                    chunk_size = constants.PYAUDIO_CHUNK_SIZE
                    for i in range(0, len(frames), chunk_size):
                        if stop_event and stop_event.is_set():
                            logger.info("Audio playback interrupted")
                            if not quiet:
                                print_with_style("⏹️ Audio playback interrupted", style="yellow")
                            break
                        chunk = frames[i : i + chunk_size]
                        stream.write(chunk)
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
    *,
    text: str,
    provider_config: config.ProviderSelection,
    audio_output_config: config.AudioOutput,
    wyoming_tts_config: config.WyomingTTS,
    openai_tts_config: config.OpenAITTS,
    openai_llm_config: config.OpenAILLM,
    logger: logging.Logger,
    quiet: bool = False,
    play_audio_flag: bool = True,
    stop_event: InteractiveStopEvent | None = None,
    live: Live,
) -> bytes | None:
    """Synthesize and optionally play speech from text."""
    synthesizer = get_synthesizer(
        provider_config,
        audio_output_config,
        wyoming_tts_config,
        openai_tts_config,
        openai_llm_config,
    )
    audio_data = None
    try:
        async with live_timer(live, "🔊 Synthesizing text", style="blue", quiet=quiet):
            audio_data = await synthesizer(
                text=text,
                wyoming_tts_config=wyoming_tts_config,
                openai_tts_config=openai_tts_config,
                openai_llm_config=openai_llm_config,
                logger=logger,
                quiet=quiet,
                live=live,
            )
    except Exception:
        logger.exception("Error during speech synthesis")
        return None

    if audio_data and play_audio_flag:
        await play_audio(
            audio_data,
            logger,
            audio_output_config=audio_output_config,
            quiet=quiet,
            stop_event=stop_event,
            live=live,
        )

    return audio_data
