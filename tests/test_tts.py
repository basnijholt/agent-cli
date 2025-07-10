"""Tests for the TTS module."""

from __future__ import annotations

import io
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.services.tts import _apply_speed_adjustment, _speak_text, get_synthesizer


@pytest.mark.asyncio
@patch("agent_cli.services.tts.get_synthesizer")
async def test_speak_text(mock_get_synthesizer: MagicMock) -> None:
    """Test the speak_text function."""
    mock_synthesizer = AsyncMock(return_value=b"audio data")
    mock_get_synthesizer.return_value = mock_synthesizer
    provider_config = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    audio_output_config = config.AudioOutput(enable_tts=True)
    wyoming_tts_config = config.WyomingTTS(
        wyoming_tts_ip="localhost",
        wyoming_tts_port=1234,
    )
    openai_tts_config = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")
    openai_llm_config = config.OpenAILLM(
        openai_llm_model="gpt-4o-mini",
        openai_api_key="test_api_key",
    )
    kokoro_tts_cfg = config.KokoroTTS(
        kokoro_tts_model="tts-1",
        kokoro_tts_voice="alloy",
        kokoro_tts_host="http://localhost:8000/v1",
    )

    audio_data = await _speak_text(
        text="hello",
        provider_config=provider_config,
        audio_output_config=audio_output_config,
        wyoming_tts_config=wyoming_tts_config,
        openai_tts_config=openai_tts_config,
        openai_llm_config=openai_llm_config,
        kokoro_tts_config=kokoro_tts_cfg,
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


def test_get_synthesizer_disabled():
    """Test that the dummy synthesizer is returned when TTS is disabled."""
    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    audio_output_config = config.AudioOutput(enable_tts=False)
    wyoming_tts_config = config.WyomingTTS(
        wyoming_tts_ip="localhost",
        wyoming_tts_port=1234,
    )
    openai_tts_config = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")
    openai_llm_config = config.OpenAILLM(
        openai_llm_model="gpt-4o-mini",
        openai_api_key="test_api_key",
    )
    kokoro_tts_cfg = config.KokoroTTS(
        kokoro_tts_model="tts-1",
        kokoro_tts_voice="alloy",
        kokoro_tts_host="http://localhost:8000/v1",
    )

    synthesizer = get_synthesizer(
        provider_config=provider_cfg,
        audio_output_config=audio_output_config,
        wyoming_tts_config=wyoming_tts_config,
        openai_tts_config=openai_tts_config,
        openai_llm_config=openai_llm_config,
        kokoro_tts_config=kokoro_tts_cfg,
    )

    assert synthesizer.__name__ == "_dummy_synthesizer"
