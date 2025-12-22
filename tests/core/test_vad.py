"""Tests for Voice Activity Detection module using Silero VAD."""

from __future__ import annotations

import struct
import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from agent_cli.core.vad import VoiceActivityDetector


@pytest.fixture
def mock_silero_vad() -> MagicMock:
    """Mock silero_vad module."""
    mock_model = MagicMock()
    mock_model.audio_forward.return_value = 0.0  # No speech by default
    return mock_model


def test_import_error_without_silero_vad() -> None:
    """Test that ImportError is raised with helpful message when silero-vad is missing."""
    import importlib  # noqa: PLC0415

    with patch.dict("sys.modules", {"torch": None, "silero_vad": None}):
        # Remove cached module
        if "agent_cli.core.vad" in sys.modules:
            del sys.modules["agent_cli.core.vad"]

        with pytest.raises(ImportError, match="agent-cli\\[vad\\]"):
            importlib.import_module("agent_cli.core.vad")


@pytest.fixture
def vad() -> VoiceActivityDetector:
    """Create a VoiceActivityDetector instance."""
    try:
        from agent_cli.core.vad import VoiceActivityDetector  # noqa: PLC0415
    except ImportError:
        pytest.skip("silero-vad not installed")
    return VoiceActivityDetector()


@pytest.fixture
def sample_audio_frame(vad: Any) -> bytes:
    """Create a sample audio frame of the correct size for VAD processing."""
    # Window size depends on sample rate: 512 samples at 16kHz, 256 at 8kHz
    # 2 bytes per sample (16-bit audio)
    window_size = vad.window_size_bytes
    # Generate silence (zeros)
    return b"\x00" * window_size


@pytest.fixture
def speech_audio_frame(vad: Any) -> bytes:
    """Create a sample audio frame that simulates speech (non-zero audio)."""
    window_size = vad.window_size_bytes
    # Generate a simple tone pattern that should trigger speech detection
    samples = []
    for i in range(window_size // 2):
        # Simple sine-ish wave pattern
        value = int(10000 * ((i % 100) / 50 - 1))
        samples.append(struct.pack("<h", value))
    return b"".join(samples)


def test_vad_initialization(vad: Any) -> None:
    """Test VAD initializes with correct defaults."""
    assert vad.threshold == 0.5
    assert vad.sample_rate == 16000
    assert vad.silence_threshold_ms == 1000
    assert vad.min_speech_duration_ms == 500


def test_vad_window_size(vad: Any) -> None:
    """Test window size calculation."""
    # Silero VAD uses 512 samples for 16kHz, 256 for 8kHz
    # 16-bit audio = 2 bytes per sample
    expected_window_size_samples = 512  # 16kHz
    expected_window_size_bytes = 512 * 2  # 1024 bytes
    assert vad.window_size_samples == expected_window_size_samples
    assert vad.window_size_bytes == expected_window_size_bytes


def test_vad_invalid_sample_rate() -> None:
    """Test that invalid sample rate raises ValueError."""
    try:
        from agent_cli.core.vad import VoiceActivityDetector  # noqa: PLC0415
    except ImportError:
        pytest.skip("silero-vad not installed")

    with pytest.raises(ValueError, match="Sample rate must be"):
        VoiceActivityDetector(sample_rate=22050)


def test_vad_process_silence(vad: Any, sample_audio_frame: bytes) -> None:
    """Test processing silent audio returns no speech."""
    is_speaking, segment = vad.process_chunk(sample_audio_frame)
    assert is_speaking is False
    assert segment is None


def test_vad_reset(vad: Any, sample_audio_frame: bytes) -> None:
    """Test VAD reset clears state."""
    # Process some audio
    vad.process_chunk(sample_audio_frame)

    # Reset
    vad.reset()

    # Check internal state is cleared
    assert vad._is_speaking is False
    assert vad._silence_samples == 0
    assert vad._speech_samples == 0


def test_vad_get_segment_duration(vad: Any) -> None:
    """Test segment duration calculation."""
    # 1 second of audio at 16kHz, 16-bit = 32000 bytes
    segment = b"\x00" * 32000
    duration = vad.get_segment_duration_seconds(segment)
    assert duration == 1.0


def test_vad_flush_with_no_speech(vad: Any, sample_audio_frame: bytes) -> None:
    """Test flush returns None when no speech was detected."""
    vad.process_chunk(sample_audio_frame)
    result = vad.flush()
    assert result is None


def test_vad_properties(vad: Any) -> None:
    """Test VAD property calculations."""
    # Silence threshold samples = 1000ms * 16000Hz / 1000 = 16000 samples
    assert vad._silence_threshold_samples == 16000

    # Min speech samples = 500ms * 16000Hz / 1000 = 8000 samples
    assert vad._min_speech_samples == 8000


def test_vad_8khz_window_size() -> None:
    """Test VAD window size at 8kHz sample rate."""
    try:
        from agent_cli.core.vad import VoiceActivityDetector  # noqa: PLC0415
    except ImportError:
        pytest.skip("silero-vad not installed")

    vad_8k = VoiceActivityDetector(sample_rate=8000)
    # Silero VAD uses 256 samples for 8kHz
    assert vad_8k.window_size_samples == 256
    assert vad_8k.window_size_bytes == 512  # 256 samples * 2 bytes


def test_vad_custom_threshold() -> None:
    """Test VAD with custom threshold."""
    try:
        from agent_cli.core.vad import VoiceActivityDetector  # noqa: PLC0415
    except ImportError:
        pytest.skip("silero-vad not installed")

    vad = VoiceActivityDetector(threshold=0.8)
    assert vad.threshold == 0.8
