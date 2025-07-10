"""Tests for the TTS module."""

from __future__ import annotations

import io
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.core.utils import InteractiveStopEvent
from agent_cli.services.tts import (
    KOKORO_STREAM_CHANNELS,
    KOKORO_STREAM_RATE,
    KOKORO_STREAM_WIDTH,
    _apply_speed_adjustment,
    _speak_text,
    _stream_and_play_kokoro,
    get_synthesizer,
)


@pytest.fixture
def mock_configs() -> tuple[
    config.ProviderSelection,
    config.AudioOutput,
    config.WyomingTTS,
    config.OpenAITTS,
    config.OpenAILLM,
    config.KokoroTTS,
]:
    """Return a tuple of mock configs."""
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
    return (
        provider_config,
        audio_output_config,
        wyoming_tts_config,
        openai_tts_config,
        openai_llm_config,
        kokoro_tts_cfg,
    )


@pytest.mark.asyncio
@patch("agent_cli.services.tts.get_synthesizer")
async def test_speak_text_non_kokoro(
    mock_get_synthesizer: MagicMock,
    mock_configs: tuple,
) -> None:
    """Test the speak_text function for non-kokoro providers."""
    (
        provider_config,
        audio_output_config,
        wyoming_tts_config,
        openai_tts_config,
        openai_llm_config,
        kokoro_tts_config,
    ) = mock_configs
    mock_synthesizer = AsyncMock(return_value=b"audio data")
    mock_get_synthesizer.return_value = mock_synthesizer

    audio_data = await _speak_text(
        text="hello",
        provider_config=provider_config,
        audio_output_config=audio_output_config,
        wyoming_tts_config=wyoming_tts_config,
        openai_tts_config=openai_tts_config,
        openai_llm_config=openai_llm_config,
        kokoro_tts_config=kokoro_tts_config,
        logger=MagicMock(),
        play_audio_flag=False,
        live=MagicMock(),
    )

    assert audio_data == b"audio data"
    mock_synthesizer.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.services.tts._stream_and_play_kokoro", new_callable=AsyncMock)
async def test_speak_text_kokoro(
    mock_stream_and_play: AsyncMock,
    mock_configs: tuple,
) -> None:
    """Test the speak_text function for the kokoro provider."""
    (
        provider_config,
        audio_output_config,
        wyoming_tts_config,
        openai_tts_config,
        openai_llm_config,
        kokoro_tts_config,
    ) = mock_configs
    provider_config.tts_provider = "kokoro"
    mock_stream_and_play.return_value = b"kokoro audio"

    audio_data = await _speak_text(
        text="hello",
        provider_config=provider_config,
        audio_output_config=audio_output_config,
        wyoming_tts_config=wyoming_tts_config,
        openai_tts_config=openai_tts_config,
        openai_llm_config=openai_llm_config,
        kokoro_tts_config=kokoro_tts_config,
        logger=MagicMock(),
        play_audio_flag=True,
        live=MagicMock(),
    )

    assert audio_data == b"kokoro audio"
    mock_stream_and_play.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.services.tts.AsyncOpenAI")
@patch("agent_cli.services.tts.pyaudio_context")
@patch("agent_cli.services.tts.open_pyaudio_stream")
async def test_stream_and_play_kokoro(
    mock_open_stream: MagicMock,
    mock_pyaudio_context: MagicMock,
    mock_async_openai: MagicMock,
    mock_configs: tuple,
) -> None:
    """Test the _stream_and_play_kokoro function."""
    (
        _,
        audio_output_config,
        _,
        _,
        _,
        kokoro_tts_config,
    ) = mock_configs

    # Mock the client instance and its call chain
    mock_client = MagicMock()
    mock_async_openai.return_value = mock_client

    # Mock the async context manager for the audio stream
    mock_stream = MagicMock()
    mock_stream.write = MagicMock()
    mock_open_stream.return_value.__aenter__.return_value = mock_stream

    # Mock the streaming response itself
    async def mock_aiter_generator():
        yield b"chunk1"
        yield b"chunk2"

    # This setup is crucial:
    # 1. The response object must be a regular MagicMock, not an AsyncMock.
    # 2. The `aiter_bytes` method on the response mock must be a regular MagicMock.
    # 3. The `return_value` of that method must be a called async generator.
    mock_response = MagicMock()
    mock_response.aiter_bytes.return_value = mock_aiter_generator()

    # The `create` method returns an async context manager.
    # We mock the object that the `async with` statement will yield.
    create_context_manager = AsyncMock()
    create_context_manager.__aenter__.return_value = mock_response
    mock_client.audio.speech.with_streaming_response.create.return_value = create_context_manager

    # --- Test with playback enabled ---
    audio_data = await _stream_and_play_kokoro(
        text="hello",
        kokoro_tts_config=kokoro_tts_config,
        audio_output_config=audio_output_config,
        logger=MagicMock(),
        play_audio_flag=True,
        stop_event=InteractiveStopEvent(),
        live=MagicMock(),
    )

    assert mock_stream.write.call_count == 2
    # Verify that the returned data is a valid WAV file
    with wave.open(io.BytesIO(audio_data), "rb") as wf:
        assert wf.getnchannels() == KOKORO_STREAM_CHANNELS
        assert wf.getsampwidth() == KOKORO_STREAM_WIDTH
        assert wf.getframerate() == KOKORO_STREAM_RATE
        assert wf.readframes(wf.getnframes()) == b"chunk1chunk2"

    # --- Test with playback disabled ---
    mock_stream.reset_mock()
    audio_data_no_play = await _stream_and_play_kokoro(
        text="hello",
        kokoro_tts_config=kokoro_tts_config,
        audio_output_config=audio_output_config,
        logger=MagicMock(),
        play_audio_flag=False,
        stop_event=InteractiveStopEvent(),
        live=MagicMock(),
    )
    mock_stream.write.assert_not_called()
    assert audio_data == audio_data_no_play


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
    assert not speed_changed


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
    assert not speed_changed


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
    mock_audio_stretch.stretch.assert_called_once_with(ratio=1 / 2.0)
    mock_audio_stretch.save_wav.assert_called_once()

    # Should return a new BytesIO object and True for speed_changed
    assert result_data is not original_data
    assert speed_changed


def test_get_synthesizer_disabled(mock_configs: tuple):
    """Test that the dummy synthesizer is returned when TTS is disabled."""
    (
        provider_config,
        audio_output_config,
        wyoming_tts_config,
        openai_tts_config,
        openai_llm_config,
        kokoro_tts_config,
    ) = mock_configs
    audio_output_config.enable_tts = False

    synthesizer = get_synthesizer(
        provider_config=provider_config,
        audio_output_config=audio_output_config,
        wyoming_tts_config=wyoming_tts_config,
        openai_tts_config=openai_tts_config,
        openai_llm_config=openai_llm_config,
        kokoro_tts_config=kokoro_tts_config,
    )

    assert synthesizer.__name__ == "_dummy_synthesizer"
