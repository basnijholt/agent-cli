"""Module for Text-to-Speech using Wyoming or OpenAI."""

from __future__ import annotations

import asyncio
import importlib.util
import io
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from rich.live import Live

from agent_cli import config, constants
from agent_cli.core.audio import open_audio_stream, setup_output_stream
from agent_cli.core.audio_format import extract_pcm_from_wav
from agent_cli.core.utils import (
    InteractiveStopEvent,
    live_timer,
    manage_send_receive_tasks,
    print_error_message,
    print_with_style,
)
from agent_cli.services import pcm_to_wav, synthesize_speech_gemini, synthesize_speech_openai
from agent_cli.services._wyoming_utils import wyoming_client_context

if TYPE_CHECKING:
    import logging
    from collections.abc import Awaitable, Callable

    from rich.live import Live
    from wyoming.client import AsyncClient
    from wyoming.tts import Synthesize


has_audiostretchy = importlib.util.find_spec("audiostretchy") is not None


def create_synthesizer(
    provider_cfg: config.ProviderSelection,
    audio_output_cfg: config.AudioOutput,
    wyoming_tts_cfg: config.WyomingTTS,
    openai_tts_cfg: config.OpenAITTS,
    kokoro_tts_cfg: config.KokoroTTS,
    gemini_tts_cfg: config.GeminiTTS | None = None,
) -> Callable[..., Awaitable[bytes | None]]:
    """Return the appropriate synthesizer based on the config."""
    if not audio_output_cfg.enable_tts:
        return _dummy_synthesizer
    if provider_cfg.tts_provider == "openai":
        return partial(
            _synthesize_speech_openai,
            openai_tts_cfg=openai_tts_cfg,
        )
    if provider_cfg.tts_provider == "kokoro":
        return partial(
            _synthesize_speech_kokoro,
            kokoro_tts_cfg=kokoro_tts_cfg,
        )
    if provider_cfg.tts_provider == "gemini":
        assert gemini_tts_cfg is not None, "Gemini TTS config required"
        return partial(_synthesize_speech_gemini, gemini_tts_cfg=gemini_tts_cfg)
    if provider_cfg.tts_provider == "wyoming":
        return partial(_synthesize_speech_wyoming, wyoming_tts_cfg=wyoming_tts_cfg)
    msg = f"Unknown TTS provider: {provider_cfg.tts_provider}"
    raise NotImplementedError(msg)


async def handle_tts_playback(
    *,
    text: str,
    provider_cfg: config.ProviderSelection,
    audio_output_cfg: config.AudioOutput,
    wyoming_tts_cfg: config.WyomingTTS,
    openai_tts_cfg: config.OpenAITTS,
    kokoro_tts_cfg: config.KokoroTTS,
    gemini_tts_cfg: config.GeminiTTS | None = None,
    save_file: Path | None,
    quiet: bool,
    logger: logging.Logger,
    play_audio: bool = True,
    status_message: str = "🔊 Speaking...",
    description: str = "Audio",
    stop_event: InteractiveStopEvent | None = None,
    live: Live,
) -> bytes | None:
    """Handle TTS synthesis, playback, and file saving."""
    try:
        if not quiet and status_message:
            print_with_style(status_message, style="blue")

        audio_data = await _speak_text(
            text=text,
            provider_cfg=provider_cfg,
            audio_output_cfg=audio_output_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
            kokoro_tts_cfg=kokoro_tts_cfg,
            gemini_tts_cfg=gemini_tts_cfg,
            logger=logger,
            quiet=quiet,
            play_audio_flag=play_audio,
            stop_event=stop_event,
            live=live,
        )

        if save_file and audio_data:
            await _save_audio_file(
                audio_data,
                save_file,
                quiet,
                logger,
                description=description,
            )

        return audio_data

    except (OSError, ConnectionError, TimeoutError) as e:
        logger.warning("Failed TTS operation: %s", e)
        if not quiet:
            print_with_style(f"⚠️ TTS failed: {e}", style="yellow")
        return None


# --- Helper Functions ---


def _create_synthesis_request(
    text: str,
    *,
    voice_name: str | None = None,
    language: str | None = None,
    speaker: str | None = None,
) -> Synthesize:
    """Create a synthesis request with optional voice parameters."""
    from wyoming.tts import Synthesize, SynthesizeVoice  # noqa: PLC0415

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
    from wyoming.audio import AudioChunk, AudioStart, AudioStop  # noqa: PLC0415

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


async def _dummy_synthesizer(**_kwargs: object) -> bytes | None:
    """A dummy synthesizer that does nothing."""
    return None


async def _synthesize_speech_openai(
    *,
    text: str,
    openai_tts_cfg: config.OpenAITTS,
    logger: logging.Logger,
    **_kwargs: object,
) -> bytes | None:
    """Synthesize speech from text using OpenAI-compatible TTS server."""
    return await synthesize_speech_openai(
        text=text,
        openai_tts_cfg=openai_tts_cfg,
        logger=logger,
    )


async def _synthesize_speech_kokoro(
    *,
    text: str,
    kokoro_tts_cfg: config.KokoroTTS,
    logger: logging.Logger,
    **_kwargs: object,
) -> bytes | None:
    """Synthesize speech from text using Kokoro TTS server via OpenAI client."""
    openai_tts_cfg = config.OpenAITTS(
        tts_openai_model=kokoro_tts_cfg.tts_kokoro_model,
        tts_openai_voice=kokoro_tts_cfg.tts_kokoro_voice,
        tts_openai_base_url=kokoro_tts_cfg.tts_kokoro_host,
    )
    try:
        return await synthesize_speech_openai(
            text=text,
            openai_tts_cfg=openai_tts_cfg,
            logger=logger,
        )
    except Exception:
        logger.exception("Error during Kokoro speech synthesis")
        return None


async def _synthesize_speech_gemini(
    *,
    text: str,
    gemini_tts_cfg: config.GeminiTTS,
    logger: logging.Logger,
    **_kwargs: object,
) -> bytes | None:
    """Synthesize speech from text using Gemini TTS."""
    return await synthesize_speech_gemini(text=text, gemini_tts_cfg=gemini_tts_cfg, logger=logger)


async def _synthesize_speech_wyoming(
    *,
    text: str,
    wyoming_tts_cfg: config.WyomingTTS,
    logger: logging.Logger,
    quiet: bool = False,
    live: Live,
    **_kwargs: object,
) -> bytes | None:
    """Synthesize speech from text using Wyoming TTS server."""
    try:
        async with wyoming_client_context(
            wyoming_tts_cfg.tts_wyoming_ip,
            wyoming_tts_cfg.tts_wyoming_port,
            "TTS",
            logger,
            quiet=quiet,
        ) as client:
            async with live_timer(live, "🔊 Synthesizing text", style="blue", quiet=quiet):
                synthesize_event = _create_synthesis_request(
                    text,
                    voice_name=wyoming_tts_cfg.tts_wyoming_voice,
                    language=wyoming_tts_cfg.tts_wyoming_language,
                    speaker=wyoming_tts_cfg.tts_wyoming_speaker,
                )
                _send_task, recv_task = await manage_send_receive_tasks(
                    client.write_event(synthesize_event.event()),
                    _process_audio_events(client, logger),
                )
                audio_data, sample_rate, sample_width, channels = recv_task.result()
            if sample_rate and sample_width and channels and audio_data:
                wav_data = pcm_to_wav(
                    audio_data,
                    sample_rate=sample_rate,
                    sample_width=sample_width,
                    channels=channels,
                )
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


async def _play_audio(
    audio_data: bytes,
    logger: logging.Logger,
    *,
    audio_output_cfg: config.AudioOutput,
    quiet: bool = False,
    stop_event: InteractiveStopEvent | None = None,
    live: Live,
) -> None:
    """Play WAV audio data using SoundDevice."""
    import numpy as np  # noqa: PLC0415

    try:
        wav_io = io.BytesIO(audio_data)
        speed = audio_output_cfg.tts_speed
        wav_io, speed_changed = _apply_speed_adjustment(wav_io, speed)
        wav = extract_pcm_from_wav(wav_io.read())
        sample_rate = wav.sample_rate if speed_changed else int(wav.sample_rate * speed)
        base_msg = f"🔊 Playing audio at {speed}x speed" if speed != 1.0 else "🔊 Playing audio"
        async with live_timer(live, base_msg, style="blue", quiet=quiet):
            stream_config = setup_output_stream(
                audio_output_cfg.output_device_index,
                sample_rate=sample_rate,
                sample_width=wav.sample_width,
                channels=wav.num_channels,
            )
            dtype = stream_config.dtype

            with open_audio_stream(stream_config) as stream:
                chunk_size_frames = constants.AUDIO_CHUNK_SIZE
                bytes_per_frame = wav.num_channels * wav.sample_width
                chunk_bytes = chunk_size_frames * bytes_per_frame

                for i in range(0, len(wav.pcm_data), chunk_bytes):
                    if stop_event and stop_event.is_set():
                        logger.info("Audio playback interrupted")
                        if not quiet:
                            print_with_style("⏹️ Audio playback interrupted", style="yellow")
                        break
                    chunk = wav.pcm_data[i : i + chunk_bytes]

                    # Convert bytes to numpy array for sounddevice
                    audio_array = np.frombuffer(chunk, dtype=dtype)
                    if wav.num_channels > 1:
                        audio_array = audio_array.reshape(-1, wav.num_channels)

                    stream.write(audio_array)
                    await asyncio.sleep(0)
        if not (stop_event and stop_event.is_set()):
            logger.info("Audio playback completed (speed: %.1fx)", speed)
            if not quiet:
                print_with_style("✅ Audio playback finished")
    except Exception as e:
        logger.exception("Error during audio playback")
        if not quiet:
            print_error_message(f"Playback error: {e}")


async def _speak_text(
    *,
    text: str,
    provider_cfg: config.ProviderSelection,
    audio_output_cfg: config.AudioOutput,
    wyoming_tts_cfg: config.WyomingTTS,
    openai_tts_cfg: config.OpenAITTS,
    kokoro_tts_cfg: config.KokoroTTS,
    gemini_tts_cfg: config.GeminiTTS | None = None,
    logger: logging.Logger,
    quiet: bool = False,
    play_audio_flag: bool = True,
    stop_event: InteractiveStopEvent | None = None,
    live: Live,
) -> bytes | None:
    """Synthesize and optionally play speech from text."""
    synthesizer = create_synthesizer(
        provider_cfg,
        audio_output_cfg,
        wyoming_tts_cfg,
        openai_tts_cfg,
        kokoro_tts_cfg,
        gemini_tts_cfg,
    )
    audio_data = None
    try:
        async with live_timer(live, "🔊 Synthesizing text", style="blue", quiet=quiet):
            audio_data = await synthesizer(
                text=text,
                wyoming_tts_cfg=wyoming_tts_cfg,
                openai_tts_cfg=openai_tts_cfg,
                kokoro_tts_cfg=kokoro_tts_cfg,
                gemini_tts_cfg=gemini_tts_cfg,
                logger=logger,
                quiet=quiet,
                live=live,
            )
    except Exception:
        logger.exception("Error during speech synthesis")
        return None

    if audio_data and play_audio_flag:
        await _play_audio(
            audio_data,
            logger,
            audio_output_cfg=audio_output_cfg,
            quiet=quiet,
            stop_event=stop_event,
            live=live,
        )

    return audio_data


async def _save_audio_file(
    audio_data: bytes,
    save_file: Path,
    quiet: bool,
    logger: logging.Logger,
    *,
    description: str = "Audio",
) -> None:
    try:
        save_path = Path(save_file)
        await asyncio.to_thread(save_path.write_bytes, audio_data)
        if not quiet:
            print_with_style(f"💾 {description} saved to {save_file}")
        logger.info("%s saved to %s", description, save_file)
    except (OSError, PermissionError) as e:
        logger.exception("Failed to save %s", description.lower())
        if not quiet:
            print_with_style(
                f"❌ Failed to save {description.lower()}: {e}",
                style="red",
            )


__all__ = ["handle_tts_playback"]
