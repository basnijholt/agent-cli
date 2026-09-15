"""Audio preparation for ASR backends that require PCM WAV input."""

from __future__ import annotations

import io
import wave

from agent_cli import constants
from agent_cli.core.audio_format import convert_audio_to_wav_format
from agent_cli.server.whisper.backends.base import InvalidAudioError


async def prepare_wav_audio(
    audio: bytes,
    source_filename: str | None,
    *,
    backend_label: str,
) -> bytes:
    """Return 16kHz mono 16-bit PCM WAV bytes, converting only when needed.

    Container validity alone is insufficient: Transformers reads samples as
    int16 mono. Normalize other sample formats before model-worker dispatch.
    Backends with their own decoders, such as faster-whisper, do not need this.
    """
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav_file:
            if (
                wav_file.getsampwidth() == constants.AUDIO_FORMAT_WIDTH
                and wav_file.getnchannels() == constants.AUDIO_CHANNELS
                and wav_file.getframerate() == constants.AUDIO_RATE
            ):
                return audio
    except (wave.Error, EOFError, RuntimeError):
        # wave can raise RuntimeError when a malformed RIFF chunk seeks past EOF.
        pass

    try:
        return await convert_audio_to_wav_format(audio, source_filename or "audio")
    except RuntimeError as exc:
        msg = (
            f"Unsupported audio format for {backend_label}. "
            "Provide a valid WAV file or install ffmpeg to convert uploads."
        )
        raise InvalidAudioError(msg) from exc
