"""Tests for the TTS module."""

from __future__ import annotations

import io
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.services.tts import _apply_speed_adjustment, _speak_text, create_synthesizer


@pytest.mark.asyncio
@patch("agent_cli.services.tts.create_synthesizer")
async def test_speak_text(mock_create_synthesizer: MagicMock) -> None:
    """Test the speak_text function."""
    mock_synthesizer = AsyncMock(return_value=b"audio data")
    mock_create_synthesizer.return_value = mock_synthesizer
    provider_cfg = config.ProviderSelection(
        asr_provider="wyoming",
        llm_provider="ollama",
        tts_provider="wyoming",
    )
    audio_output_cfg = config.AudioOutput(enable_tts=True)
    wyoming_tts_cfg = config.WyomingTTS(
        tts_wyoming_ip="localhost",
        tts_wyoming_port=1234,
    )
    openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
    kokoro_tts_cfg = config.KokoroTTS(
        tts_kokoro_model="tts-1",
        tts_kokoro_voice="alloy",
        tts_kokoro_host="http://localhost:8000/v1",
    )

    audio_data = await _speak_text(
        text="hello",
        provider_cfg=provider_cfg,
        audio_output_cfg=audio_output_cfg,
        wyoming_tts_cfg=wyoming_tts_cfg,
        openai_tts_cfg=openai_tts_cfg,
        kokoro_tts_cfg=kokoro_tts_cfg,
        logger=MagicMock(),
        play_audio_flag=False,
        live=MagicMock(),
    )

    assert audio_data == b"audio data"
    mock_synthesizer.assert_called_once()


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


@patch("agent_cli.services.tts.has_audiostretchy", new=False)
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


@patch("agent_cli.services.tts.has_audiostretchy", new=True)
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


def test_create_synthesizer_disabled():
    """Test that the dummy synthesizer is returned when TTS is disabled."""
    provider_cfg = config.ProviderSelection(
        asr_provider="wyoming",
        llm_provider="ollama",
        tts_provider="wyoming",
    )
    audio_output_cfg = config.AudioOutput(enable_tts=False)
    wyoming_tts_cfg = config.WyomingTTS(
        tts_wyoming_ip="localhost",
        tts_wyoming_port=1234,
    )
    openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
    kokoro_tts_cfg = config.KokoroTTS(
        tts_kokoro_model="tts-1",
        tts_kokoro_voice="alloy",
        tts_kokoro_host="http://localhost:8000/v1",
    )

    synthesizer = create_synthesizer(
        provider_cfg=provider_cfg,
        audio_output_cfg=audio_output_cfg,
        wyoming_tts_cfg=wyoming_tts_cfg,
        openai_tts_cfg=openai_tts_cfg,
        kokoro_tts_cfg=kokoro_tts_cfg,
    )

    assert synthesizer.__name__ == "_dummy_synthesizer"
