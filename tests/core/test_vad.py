"""Tests for Voice Activity Detection module using Silero VAD."""

from __future__ import annotations

import struct
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

# Skip all tests in this module on Windows - silero-vad-lite can hang during initialization
if sys.platform == "win32":
    pytest.skip(
        "silero-vad-lite initialization can hang on Windows CI",
        allow_module_level=True,
    )

from agent_cli.core.vad import VoiceActivityDetector

if TYPE_CHECKING:
    from typing import Any


@pytest.fixture
def mock_silero_vad() -> MagicMock:
    """Mock silero_vad module."""
    mock_model = MagicMock()
    mock_model.audio_forward.return_value = 0.0  # No speech by default
    return mock_model


def test_import_error_without_silero_vad() -> None:
    """Test that ImportError is raised with helpful message when silero-vad-lite is missing."""
    import importlib  # noqa: PLC0415

    with patch.dict("sys.modules", {"silero_vad_lite": None}):
        # Remove cached module
        if "agent_cli.core.vad" in sys.modules:
            del sys.modules["agent_cli.core.vad"]

        with pytest.raises(ImportError, match="agent-cli\\[vad\\]"):
            importlib.import_module("agent_cli.core.vad")


@pytest.fixture
def vad() -> VoiceActivityDetector:
    """Create a VoiceActivityDetector instance."""
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


def test_vad_initialization(vad: VoiceActivityDetector) -> None:
    """Test VAD initializes with correct defaults."""
    assert vad.threshold == 0.3
    assert vad.sample_rate == 16000
    assert vad.silence_threshold_ms == 1000
    assert vad.min_speech_duration_ms == 250


def test_vad_window_size(vad: VoiceActivityDetector) -> None:
    """Test window size calculation."""
    # Silero VAD uses 512 samples for 16kHz, 256 for 8kHz
    # 16-bit audio = 2 bytes per sample
    expected_window_size_samples = 512  # 16kHz
    expected_window_size_bytes = 512 * 2  # 1024 bytes
    assert vad.window_size_samples == expected_window_size_samples
    assert vad.window_size_bytes == expected_window_size_bytes


def test_vad_invalid_sample_rate() -> None:
    """Test that invalid sample rate raises ValueError."""
    with pytest.raises(ValueError, match="Sample rate must be"):
        VoiceActivityDetector(sample_rate=22050)


def test_vad_process_silence(vad: VoiceActivityDetector, sample_audio_frame: bytes) -> None:
    """Test processing silent audio returns no speech."""
    is_speaking, segment = vad.process_chunk(sample_audio_frame)
    assert is_speaking is False
    assert segment is None


def test_vad_reset(vad: VoiceActivityDetector, sample_audio_frame: bytes) -> None:
    """Test VAD reset clears state."""
    # Process some audio
    vad.process_chunk(sample_audio_frame)

    # Reset
    vad.reset()

    # Check internal state is cleared
    assert vad._is_speaking is False
    assert vad._silence_samples == 0
    assert vad._speech_samples == 0


def test_vad_get_segment_duration(vad: VoiceActivityDetector) -> None:
    """Test segment duration calculation."""
    # 1 second of audio at 16kHz, 16-bit = 32000 bytes
    segment = b"\x00" * 32000
    duration = vad.get_segment_duration_seconds(segment)
    assert duration == 1.0


def test_vad_flush_with_no_speech(
    vad: VoiceActivityDetector,
    sample_audio_frame: bytes,
) -> None:
    """Test flush returns None when no speech was detected."""
    vad.process_chunk(sample_audio_frame)
    result = vad.flush()
    assert result is None


def test_vad_properties(vad: VoiceActivityDetector) -> None:
    """Test VAD property calculations."""
    # Silence threshold samples = 1000ms * 16000Hz / 1000 = 16000 samples
    assert vad._silence_threshold_samples == 16000

    # Min speech samples = 250ms * 16000Hz / 1000 = 4000 samples
    assert vad._min_speech_samples == 4000


def test_vad_8khz_window_size() -> None:
    """Test VAD window size at 8kHz sample rate."""
    vad_8k = VoiceActivityDetector(sample_rate=8000)
    # Silero VAD uses 256 samples for 8kHz
    assert vad_8k.window_size_samples == 256
    assert vad_8k.window_size_bytes == 512  # 256 samples * 2 bytes


def test_vad_custom_threshold() -> None:
    """Test VAD with custom threshold."""
    vad = VoiceActivityDetector(threshold=0.8)
    assert vad.threshold == 0.8


def test_vad_speech_detection_triggers_speaking_state(vad: VoiceActivityDetector) -> None:
    """Test that speech detection sets is_speaking to True."""
    # Mock the _is_speech method to return True
    with patch.object(vad, "_is_speech", return_value=True):
        is_speaking, segment = vad.process_chunk(b"\x00" * vad.window_size_bytes)

    assert is_speaking is True
    assert segment is None  # No segment yet, still speaking
    assert vad._is_speaking is True
    assert vad._speech_samples == vad.window_size_samples


def test_vad_speech_then_silence_produces_segment(vad: VoiceActivityDetector) -> None:
    """Test that speech followed by sufficient silence produces a completed segment."""
    # Use short thresholds for faster test
    vad.silence_threshold_ms = 100  # 100ms silence threshold
    vad.min_speech_duration_ms = 50  # 50ms min speech

    window = b"\x00" * vad.window_size_bytes

    # Simulate speech for enough windows to exceed min_speech_duration
    speech_windows_needed = (vad._min_speech_samples // vad.window_size_samples) + 1
    with patch.object(vad, "_is_speech", return_value=True):
        for _ in range(speech_windows_needed):
            is_speaking, segment = vad.process_chunk(window)
            assert is_speaking is True
            assert segment is None

    # Now simulate silence for enough windows to trigger segment completion
    silence_windows_needed = (vad._silence_threshold_samples // vad.window_size_samples) + 1
    with patch.object(vad, "_is_speech", return_value=False):
        for i in range(silence_windows_needed):
            is_speaking, segment = vad.process_chunk(window)
            if i < silence_windows_needed - 1:
                # Still waiting for silence threshold
                assert segment is None
            else:
                # Segment should be complete
                assert segment is not None
                assert is_speaking is False


def test_vad_short_speech_discarded(vad: VoiceActivityDetector) -> None:
    """Test that speech shorter than min_speech_duration is discarded."""
    # Use short thresholds for faster test
    vad.silence_threshold_ms = 100
    vad.min_speech_duration_ms = 500  # 500ms min - hard to reach

    window = b"\x00" * vad.window_size_bytes

    # Simulate just 1 window of speech (not enough)
    with patch.object(vad, "_is_speech", return_value=True):
        vad.process_chunk(window)

    # Simulate enough silence to trigger segment check
    silence_windows = (vad._silence_threshold_samples // vad.window_size_samples) + 1
    with patch.object(vad, "_is_speech", return_value=False):
        for _ in range(silence_windows):
            _is_speaking, segment = vad.process_chunk(window)

    # Segment should be None because speech was too short
    assert segment is None


def test_vad_flush_returns_speech_when_speaking(vad: VoiceActivityDetector) -> None:
    """Test that flush returns buffered speech when in speaking state."""
    vad.min_speech_duration_ms = 50  # Low threshold for test

    window = b"\x00" * vad.window_size_bytes

    # Simulate enough speech to exceed min_speech_duration
    speech_windows = (vad._min_speech_samples // vad.window_size_samples) + 1
    with patch.object(vad, "_is_speech", return_value=True):
        for _ in range(speech_windows):
            vad.process_chunk(window)

    assert vad._is_speaking is True

    # Flush should return the buffered speech
    result = vad.flush()
    assert result is not None
    assert len(result) > 0

    # After flush, state should be reset
    assert vad._is_speaking is False


def test_vad_pre_speech_buffer_included(vad: VoiceActivityDetector) -> None:
    """Test that pre-speech buffer is included when speech starts."""
    window = b"\x00" * vad.window_size_bytes

    # First, send some silence to fill pre-speech buffer
    with patch.object(vad, "_is_speech", return_value=False):
        for _ in range(3):
            vad.process_chunk(window)

    pre_speech_count = len(vad._pre_speech_buffer)
    assert pre_speech_count > 0  # Should have some pre-speech buffered

    # Now trigger speech - pre-speech buffer should be prepended
    with patch.object(vad, "_is_speech", return_value=True):
        vad.process_chunk(window)

    # Pre-speech buffer should be cleared (moved to audio buffer)
    assert len(vad._pre_speech_buffer) == 0
    # Audio buffer should contain pre-speech + current window
    expected_size = (pre_speech_count + 1) * vad.window_size_bytes
    assert len(vad._audio_buffer) == expected_size


def test_vad_silence_during_speech_accumulates(vad: VoiceActivityDetector) -> None:
    """Test that silence during speech accumulates in silence counter."""
    vad.silence_threshold_ms = 500  # 500ms silence threshold

    window = b"\x00" * vad.window_size_bytes

    # Start speaking
    with patch.object(vad, "_is_speech", return_value=True):
        vad.process_chunk(window)

    assert vad._is_speaking is True
    assert vad._silence_samples == 0

    # Now silence (but not enough to end segment)
    with patch.object(vad, "_is_speech", return_value=False):
        vad.process_chunk(window)

    # Should still be speaking, but silence counter increased
    assert vad._is_speaking is True
    assert vad._silence_samples == vad.window_size_samples

    # Speech again should reset silence counter
    with patch.object(vad, "_is_speech", return_value=True):
        vad.process_chunk(window)

    assert vad._silence_samples == 0
