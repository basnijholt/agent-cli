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
                "-y",
                "-i",
                str(input_path),
                "-f",
                "s16le",
                "-ar",
                str(constants.AUDIO_RATE),
                "-ac",
                str(constants.AUDIO_CHANNELS),
                str(output_path),
            ]

            logger.debug("Running FFmpeg command: %s", " ".join(cmd))

            # Run FFmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                check=False,
            )

            if result.returncode != 0:
                stderr_text = result.stderr.decode("utf-8", errors="replace")
                logger.error("FFmpeg failed with return code %d", result.returncode)
                logger.error("FFmpeg stderr: %s", stderr_text)
                msg = f"FFmpeg conversion failed: {stderr_text}"
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


def save_audio_as_mp3(
    audio_data: bytes,
    output_path: Path,
    sample_rate: int = constants.AUDIO_RATE,
    channels: int = constants.AUDIO_CHANNELS,
    bitrate: str = "64k",
) -> Path:
    """Convert raw PCM audio data to MP3 format using FFmpeg.

    Args:
        audio_data: Raw PCM audio data (16-bit signed little-endian).
        output_path: Path where the MP3 file will be saved.
        sample_rate: Audio sample rate in Hz.
        channels: Number of audio channels.
        bitrate: MP3 bitrate (e.g., "128k", "192k", "256k").

    Returns:
        Path to the saved MP3 file.

    Raises:
        RuntimeError: If FFmpeg is not available or conversion fails.

    """
    if not shutil.which("ffmpeg"):
        msg = "FFmpeg not found in PATH. Please install FFmpeg for MP3 conversion."
        raise RuntimeError(msg)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Use a temporary file for the raw PCM input
    with tempfile.NamedTemporaryFile(delete=False, suffix=".raw") as input_file:
        input_path = Path(input_file.name)

        try:
            # Write raw PCM data
            input_file.write(audio_data)
            input_file.flush()

            # Build FFmpeg command
            # Input: raw PCM (s16le = 16-bit signed little-endian)
            # Output: MP3 with specified bitrate
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file
                "-f",
                "s16le",  # Input format: raw PCM
                "-ar",
                str(sample_rate),  # Input sample rate
                "-ac",
                str(channels),  # Input channels
                "-i",
                str(input_path),  # Input file
                "-b:a",
                bitrate,  # Audio bitrate
                "-q:a",
                "2",  # Quality setting (0-9, lower is better)
                str(output_path),  # Output file
            ]

            logger.debug("Running FFmpeg MP3 conversion: %s", " ".join(cmd))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                check=False,
            )

            if result.returncode != 0:
                stderr_text = result.stderr.decode("utf-8", errors="replace")
                logger.error("FFmpeg MP3 conversion failed: %s", stderr_text)
                msg = f"FFmpeg MP3 conversion failed: {stderr_text}"
                raise RuntimeError(msg)

            logger.debug("Saved MP3 to %s", output_path)
            return output_path

        finally:
            # Clean up temporary input file
            input_path.unlink(missing_ok=True)
