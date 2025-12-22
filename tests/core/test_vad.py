"""Tests for Voice Activity Detection module."""

from __future__ import annotations

import struct
import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from agent_cli.core.vad import VoiceActivityDetector


@pytest.fixture
def mock_webrtcvad() -> MagicMock:
    """Mock webrtcvad module."""
    mock_vad = MagicMock()
    mock_vad.Vad.return_value = mock_vad
    mock_vad.is_speech.return_value = False
    return mock_vad


def test_import_error_without_webrtcvad() -> None:
    """Test that ImportError is raised with helpful message when webrtcvad is missing."""
    import importlib  # noqa: PLC0415

    with patch.dict("sys.modules", {"webrtcvad": None}):
        # Remove cached module
        if "agent_cli.core.vad" in sys.modules:
            del sys.modules["agent_cli.core.vad"]

        with pytest.raises(ImportError, match="agent-cli\\[daemon\\]"):
            importlib.import_module("agent_cli.core.vad")


@pytest.fixture
def vad() -> VoiceActivityDetector:
    """Create a VoiceActivityDetector instance."""
    try:
        from agent_cli.core.vad import VoiceActivityDetector  # noqa: PLC0415
    except ImportError:
        pytest.skip("webrtcvad not installed")
    return VoiceActivityDetector()


@pytest.fixture
def sample_audio_frame(vad: Any) -> bytes:
    """Create a sample audio frame of the correct size for VAD processing."""
    # Frame size depends on sample rate and frame duration
    # 16kHz, 30ms = 480 samples = 960 bytes (16-bit)
    frame_size = vad.frame_size_bytes
    # Generate silence (zeros)
    return b"\x00" * frame_size


@pytest.fixture
def speech_audio_frame(vad: Any) -> bytes:
    """Create a sample audio frame that simulates speech (non-zero audio)."""
    frame_size = vad.frame_size_bytes
    # Generate a simple tone pattern that should trigger speech detection
    samples = []
    for i in range(frame_size // 2):
        # Simple sine-ish wave pattern
        value = int(10000 * ((i % 100) / 50 - 1))
        samples.append(struct.pack("<h", value))
    return b"".join(samples)


def test_vad_initialization(vad: Any) -> None:
    """Test VAD initializes with correct defaults."""
    assert vad.aggressiveness == 2
    assert vad.sample_rate == 16000
    assert vad.frame_duration_ms == 30
    assert vad.silence_threshold_ms == 1000
    assert vad.min_speech_duration_ms == 500


def test_vad_frame_size(vad: Any) -> None:
    """Test frame size calculation."""
    # 16kHz * 30ms = 480 samples * 2 bytes = 960 bytes
    expected_frame_size = 16000 * 30 // 1000 * 2
    assert vad.frame_size_bytes == expected_frame_size


def test_vad_invalid_aggressiveness() -> None:
    """Test that invalid aggressiveness raises ValueError."""
    try:
        from agent_cli.core.vad import VoiceActivityDetector  # noqa: PLC0415
    except ImportError:
        pytest.skip("webrtcvad not installed")

    with pytest.raises(ValueError, match="Aggressiveness must be 0-3"):
        VoiceActivityDetector(aggressiveness=5)


def test_vad_invalid_sample_rate() -> None:
    """Test that invalid sample rate raises ValueError."""
    try:
        from agent_cli.core.vad import VoiceActivityDetector  # noqa: PLC0415
    except ImportError:
        pytest.skip("webrtcvad not installed")

    with pytest.raises(ValueError, match="Sample rate must be"):
        VoiceActivityDetector(sample_rate=22050)


def test_vad_invalid_frame_duration() -> None:
    """Test that invalid frame duration raises ValueError."""
    try:
        from agent_cli.core.vad import VoiceActivityDetector  # noqa: PLC0415
    except ImportError:
        pytest.skip("webrtcvad not installed")

    with pytest.raises(ValueError, match="Frame duration must be"):
        VoiceActivityDetector(frame_duration_ms=25)


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
    assert vad._silence_frames == 0
    assert vad._speech_frames == 0


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
    # Silence threshold frames = 1000ms / 30ms = 33 frames
    assert vad._silence_threshold_frames == 33

    # Min speech frames = 500ms / 30ms = 16 frames
    assert vad._min_speech_frames == 16
