"""Tests for audio format conversion utilities."""

from __future__ import annotations

import shutil
import struct
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.core import audio_format


@pytest.fixture
def sample_wav_data() -> bytes:
    """Create a minimal valid WAV file header + silence.

    Simplified minimal 44 bytes header for 44.1kHz mono 16-bit.
    """
    sample_rate = 44100
    channels = 1
    duration_s = 0.1
    num_samples = int(sample_rate * duration_s)
    data_size = num_samples * channels * 2  # 2 bytes per sample (16 bit)

    # RIFF header
    header = b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
    header += b"fmt " + struct.pack(
        "<IHHIIHH",
        16,
        1,
        channels,
        sample_rate,
        sample_rate * 2,
        2,
        16,
    )
    header += b"data" + struct.pack("<I", data_size)

    data = b"\x00" * data_size
    return header + data


def test_ffmpeg_not_available() -> None:
    """Test that RuntimeError is raised if ffmpeg is missing."""
    with (
        patch("shutil.which", return_value=None),
        pytest.raises(RuntimeError, match="FFmpeg not found"),
    ):
        audio_format.convert_audio_to_wyoming_format(b"data", "test.wav")


def test_convert_audio_arguments() -> None:
    """Regression test: Ensure subprocess.run is called with text=False."""
    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("subprocess.run") as mock_run,
        patch("pathlib.Path.read_bytes", return_value=b"converted_data"),
        patch("pathlib.Path.unlink"),  # Prevent file deletion issues on Windows
    ):
        # Setup mock to simulate success
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")

        audio_format.convert_audio_to_wyoming_format(b"input_data", "test.mp3")

        # Check that subprocess.run was called
        assert mock_run.called
        args, kwargs = mock_run.call_args

        # CRITICAL: Verify text=False (or not present/True) was passed
        # The fix explicitly sets text=False
        assert kwargs.get("text") is False, "subprocess.run must be called with text=False"

        # Verify command structure
        cmd = args[0]
        assert cmd[0] == "ffmpeg"
        assert "-f" in cmd
        assert "s16le" in cmd


def test_convert_audio_integration(sample_wav_data: bytes) -> None:
    """Integration test using actual ffmpeg if available."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not found")

    try:
        converted = audio_format.convert_audio_to_wyoming_format(
            sample_wav_data,
            "test.wav",
        )

        # Wyoming format is 16kHz, 16-bit, mono (2 bytes per sample)
        # Check if output seems reasonable (non-empty)
        assert len(converted) > 0

        # Ideally check if it's multiple of 2 (16-bit)
        assert len(converted) % 2 == 0

    except RuntimeError as e:
        pytest.fail(f"Conversion failed: {e}")
