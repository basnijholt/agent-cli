"""Audio format conversion utilities using FFmpeg."""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import NamedTuple

from agent_cli import constants

logger = logging.getLogger(__name__)

VALID_EXTENSIONS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm")


class WavPcmData(NamedTuple):
    """PCM data and parameters extracted from a WAV file."""

    pcm_data: bytes
    sample_rate: int
    num_channels: int
    sample_width: int


def extract_pcm_from_wav(wav_bytes: bytes) -> WavPcmData:
    """Extract raw PCM data and WAV parameters from WAV bytes.

    Args:
        wav_bytes: WAV file data as bytes.

    Returns:
        WavPcmData with pcm_data, sample_rate, num_channels, sample_width.

    Raises:
        wave.Error: If the data is not a valid WAV file.

    """
    with io.BytesIO(wav_bytes) as buf, wave.open(buf, "rb") as wav_file:
        return WavPcmData(
            pcm_data=wav_file.readframes(wav_file.getnframes()),
            sample_rate=wav_file.getframerate(),
            num_channels=wav_file.getnchannels(),
            sample_width=wav_file.getsampwidth(),
        )


def is_valid_audio_file(value: object) -> bool:
    """Check if the provided value is a valid audio file.

    Works with FastAPI UploadFile or any object with filename and content_type attributes.

    Args:
        value: Object to check (typically an UploadFile).

    Returns:
        True if the object appears to be a valid audio file.

    """
    filename = getattr(value, "filename", None)
    content_type = getattr(value, "content_type", None)

    if not filename and not content_type:
        return False

    if content_type and content_type.startswith("audio/"):
        return True
    return bool(filename and str(filename).lower().endswith(VALID_EXTENSIONS))


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


def _run_ffmpeg(
    cmd: list[str],
    timeout: int | None,
) -> None:
    """Run ffmpeg command with error handling."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        msg = f"FFmpeg conversion timed out after {timeout} seconds"
        raise RuntimeError(msg) from e

    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        logger.error("FFmpeg MP3 conversion failed: %s", stderr_text)
        msg = f"FFmpeg MP3 conversion failed: {stderr_text}"
        raise RuntimeError(msg)


def convert_to_mp3(
    audio_data: bytes,
    *,
    input_format: str = "wav",
    sample_rate: int | None = None,
    channels: int | None = None,
    bitrate: str = "128k",
    timeout: int | None = 60,
) -> bytes:
    """Convert audio data to MP3 format using FFmpeg.

    Args:
        audio_data: Audio data as bytes.
        input_format: Input format - "wav" (auto-detected) or "pcm" (raw s16le).
        sample_rate: Sample rate in Hz (required if input_format is "pcm").
        channels: Number of channels (required if input_format is "pcm").
        bitrate: MP3 bitrate (e.g., "128k", "192k").
        timeout: Timeout in seconds for FFmpeg, or None for no timeout.

    Returns:
        MP3 audio data as bytes.

    Raises:
        RuntimeError: If FFmpeg is not available or conversion fails.
        ValueError: If input_format is "pcm" but sample_rate or channels not provided.

    """
    if input_format == "pcm" and (sample_rate is None or channels is None):
        msg = "sample_rate and channels are required when input_format is 'pcm'"
        raise ValueError(msg)

    if not shutil.which("ffmpeg"):
        msg = "FFmpeg not found in PATH. Please install FFmpeg for MP3 conversion."
        raise RuntimeError(msg)

    input_suffix = ".wav" if input_format == "wav" else ".raw"
    tmp_dir = Path(tempfile.mkdtemp())
    input_path = tmp_dir / f"input{input_suffix}"
    output_path = tmp_dir / "output.mp3"

    try:
        input_path.write_bytes(audio_data)

        cmd = ["ffmpeg", "-y"]
        if input_format == "pcm":
            cmd.extend(["-f", "s16le", "-ar", str(sample_rate), "-ac", str(channels)])
        cmd.extend(["-i", str(input_path), "-b:a", bitrate, "-q:a", "2", str(output_path)])

        logger.debug("Running FFmpeg MP3 conversion: %s", " ".join(cmd))
        _run_ffmpeg(cmd, timeout)

        return output_path.read_bytes()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def save_audio_as_mp3(
    audio_data: bytes,
    output_path: Path,
    sample_rate: int = constants.AUDIO_RATE,
    channels: int = constants.AUDIO_CHANNELS,
    bitrate: str = "64k",
) -> Path:
    """Convert raw PCM audio data to MP3 format and save to file.

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
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mp3_data = convert_to_mp3(
        audio_data,
        input_format="pcm",
        sample_rate=sample_rate,
        channels=channels,
        bitrate=bitrate,
        timeout=None,
    )

    output_path.write_bytes(mp3_data)
    logger.debug("Saved MP3 to %s", output_path)
    return output_path
