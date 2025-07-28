"""Audio format conversion utilities using FFmpeg."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from agent_cli import constants

logger = logging.getLogger(__name__)

VALID_EXTENSIONS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm")


def convert_audio_to_wyoming_format(
    audio_data: bytes,
    source_filename: str,
) -> bytes:
    """Convert audio data to Wyoming-compatible format using FFmpeg.

    Args:
        audio_data: Raw audio data
        source_filename: Source filename to help FFmpeg detect format

    Returns:
        Converted audio data as raw PCM bytes (16kHz, 16-bit, mono)

    Raises:
        RuntimeError: If FFmpeg is not available or conversion fails

    """
    # Check if FFmpeg is available
    if not shutil.which("ffmpeg"):
        msg = "FFmpeg not found in PATH. Please install FFmpeg to convert audio formats."
        raise RuntimeError(msg)

    # Create temporary files for input and output
    suffix = _get_file_extension(source_filename)
    with (
        tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as input_file,
        tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as output_file,
    ):
        input_path = Path(input_file.name)
        output_path = Path(output_file.name)

        try:
            # Write input audio data
            input_file.write(audio_data)
            input_file.flush()

            # Build FFmpeg command to convert to Wyoming format
            # -f s16le: 16-bit signed little-endian PCM
            # -ar 16000: 16kHz sample rate
            # -ac 1: mono (1 channel)
            cmd = [
                "ffmpeg",
                "-i",
                str(input_path),
                "-f",
                "s16le",
                "-ar",
                str(constants.PYAUDIO_RATE),
                "-ac",
                str(constants.PYAUDIO_CHANNELS),
                "-y",  # Overwrite output file
                str(output_path),
            ]

            logger.debug("Running FFmpeg command: %s", " ".join(cmd))

            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                logger.error("FFmpeg failed with return code %d", result.returncode)
                logger.error("FFmpeg stderr: %s", result.stderr)
                msg = f"FFmpeg conversion failed: {result.stderr}"
                raise RuntimeError(msg)

            # Read converted audio data
            return output_path.read_bytes()

        finally:
            # Clean up temporary files
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)


def _get_file_extension(filename: str) -> str:
    """Get file extension from filename, defaulting to .tmp.

    Args:
        filename: Source filename

    Returns:
        File extension including the dot

    """
    filename = str(filename).lower()

    for ext in VALID_EXTENSIONS:
        if filename.endswith(ext):
            return ext

    return ".tmp"


def check_ffmpeg_available() -> bool:
    """Check if FFmpeg is available in the system PATH.

    Returns:
        True if FFmpeg is available, False otherwise

    """
    return shutil.which("ffmpeg") is not None
