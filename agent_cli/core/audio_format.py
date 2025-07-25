"""Audio format conversion utilities."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from pydub import AudioSegment

from agent_cli import constants

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def convert_audio_to_wyoming_format(
    audio_data: bytes,
    source_format: str | None = None,
) -> bytes:
    """Convert audio data to Wyoming-compatible format.

    Args:
        audio_data: Raw audio data
        source_format: Source format (e.g., 'm4a', 'mp3'). If None, pydub will try to detect.

    Returns:
        Converted audio data as raw PCM bytes (16kHz, 16-bit, mono)

    """
    # Load audio from bytes
    try:
        if source_format:
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format=source_format)
        else:
            # Let pydub detect the format
            audio = AudioSegment.from_file(io.BytesIO(audio_data))

        # Convert to Wyoming format
        audio = audio.set_frame_rate(constants.PYAUDIO_RATE)  # 16kHz
        audio = audio.set_channels(constants.PYAUDIO_CHANNELS)  # Mono
        audio = audio.set_sample_width(2)  # 16-bit

        # Export as raw PCM
        return audio.raw_data

    except Exception:
        logger.exception("Failed to convert audio format")
        raise


def get_audio_format_from_filename(filename: str | Path) -> str | None:
    """Get audio format from filename extension.

    Args:
        filename: Audio filename

    Returns:
        Format string (e.g., 'm4a', 'mp3') or None if unknown

    """
    if not filename:
        return None

    filename = str(filename).lower()

    # Map common extensions to pydub format names
    format_map = {
        ".m4a": "m4a",
        ".mp4": "mp4",
        ".mp3": "mp3",
        ".wav": "wav",
        ".flac": "flac",
        ".ogg": "ogg",
        ".aac": "aac",
        ".wma": "wma",
        ".webm": "webm",
    }

    for ext, fmt in format_map.items():
        if filename.endswith(ext):
            return fmt

    return None
