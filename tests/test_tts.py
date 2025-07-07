"""Tests for the TTS module."""

from __future__ import annotations

import io
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.tts import _apply_speed_adjustment, speak_text


@pytest.mark.asyncio
@patch("agent_cli.tts._synthesize_speech", new_callable=AsyncMock)
async def test_speak_text(mock_synthesize_speech: AsyncMock) -> None:
    """Test the speak_text function."""
    mock_synthesize_speech.return_value = b"audio data"
    audio_data = await speak_text(
        text="hello",
        tts_server_ip="localhost",
        tts_server_port=1234,
        voice_name="test-voice",
        language=None,
        speaker=None,
        output_device_index=None,
        play_audio_flag=False,
        logger=MagicMock(),
        live=MagicMock(),
    )
    assert audio_data == b"audio data"


def test_apply_speed_adjustment_no_change() -> None:
    """Test that speed adjustment returns original data when speed is 1.0."""
    # Create a simple WAV file
    wav_data = io.BytesIO()
    with wave.open(wav_data, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x01" * 100)  # Simple test data

    original_data = io.BytesIO(wav_data.getvalue())
    result_data, speed_changed = _apply_speed_adjustment(original_data, 1.0)

    # Should return the same BytesIO object and False for speed_changed
    assert result_data is original_data
    assert speed_changed is False


@patch("agent_cli.tts.has_audiostretchy", new=False)
def test_apply_speed_adjustment_without_audiostretchy() -> None:
    """Test speed adjustment when AudioStretchy is not available."""
    # Create a simple WAV file
    wav_data = io.BytesIO()
    with wave.open(wav_data, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x01" * 100)

    original_data = io.BytesIO(wav_data.getvalue())
    result_data, speed_changed = _apply_speed_adjustment(original_data, 2.0)

    # Should return the same BytesIO object and False for speed_changed
    assert result_data is original_data
    assert speed_changed is False


@patch("agent_cli.tts.has_audiostretchy", new=True)
@patch("audiostretchy.stretch.AudioStretch")
def test_apply_speed_adjustment_with_audiostretchy(mock_audio_stretch_class: MagicMock) -> None:
    """Test speed adjustment with AudioStretchy available."""
    # Create a simple WAV file
    wav_data = io.BytesIO()
    with wave.open(wav_data, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x01" * 100)

    original_data = io.BytesIO(wav_data.getvalue())

    # Mock AudioStretchy behavior
    mock_audio_stretch = MagicMock()
    mock_audio_stretch_class.return_value = mock_audio_stretch

    result_data, speed_changed = _apply_speed_adjustment(original_data, 2.0)

    # Verify AudioStretchy was used correctly
    mock_audio_stretch.open.assert_called_once()
    mock_audio_stretch.stretch.assert_called_once_with(ratio=1 / 2.0)  # Note: ratio is inverted
    mock_audio_stretch.save_wav.assert_called_once()

    # Should return a new BytesIO object and True for speed_changed
    assert result_data is not original_data
    assert speed_changed is True
