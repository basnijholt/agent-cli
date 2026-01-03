"""Unit tests for the asr module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wyoming.asr import Transcribe, Transcript, TranscriptChunk
from wyoming.audio import AudioChunk, AudioStart, AudioStop

from agent_cli import config
from agent_cli.services import asr, transcribe_audio_gemini, transcribe_audio_openai


@pytest.mark.asyncio
async def test_send_audio() -> None:
    """Test that _send_audio sends the correct events."""
    # Arrange
    client = AsyncMock()
    stream = MagicMock()
    stop_event = MagicMock()
    stop_event.is_set.side_effect = [False, True]  # Allow one iteration then stop
    stop_event.ctrl_c_pressed = False

    mock_data = MagicMock()
    mock_data.tobytes.return_value = b"fake_audio_chunk"
    stream.read.return_value = (mock_data, False)
    logger = MagicMock()

    # Act
    # No need to create a task and sleep, just await the coroutine.
    # The side_effect will stop the loop.
    await asr._send_audio(
        client,
        stream,
        stop_event,
        logger,
        live=MagicMock(),
        quiet=False,
        save_recording=False,
    )

    # Assert
    assert client.write_event.call_count == 4
    client.write_event.assert_any_call(Transcribe().event())
    client.write_event.assert_any_call(
        AudioStart(rate=16000, width=2, channels=1).event(),
    )
    client.write_event.assert_any_call(
        AudioChunk(
            rate=16000,
            width=2,
            channels=1,
            audio=b"fake_audio_chunk",
        ).event(),
    )
    client.write_event.assert_any_call(AudioStop().event())


@pytest.mark.asyncio
async def test_receive_text() -> None:
    """Test that receive_transcript correctly processes events."""
    # Arrange
    client = AsyncMock()
    client.read_event.side_effect = [
        TranscriptChunk(text="hello").event(),
        Transcript(text="hello world").event(),
        None,  # To stop the loop
    ]
    logger = MagicMock()
    chunk_callback = MagicMock()
    final_callback = MagicMock()

    # Act
    result = await asr._receive_transcript(
        client,
        logger,
        chunk_callback=chunk_callback,
        final_callback=final_callback,
    )

    # Assert
    assert result == "hello world"
    chunk_callback.assert_called_once_with("hello")
    final_callback.assert_called_once_with("hello world")


def test_create_transcriber():
    """Test that the correct transcriber is returned."""
    provider_cfg = MagicMock()

    # OpenAI uses generic transcriber with transcribe_audio_openai
    provider_cfg.asr_provider = "openai"
    transcriber = asr.create_transcriber(
        provider_cfg,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    assert transcriber.func is asr._transcribe_live_audio_buffered
    assert transcriber.keywords["transcribe_fn"] is transcribe_audio_openai

    # Wyoming uses its own streaming implementation
    provider_cfg.asr_provider = "wyoming"
    transcriber = asr.create_transcriber(
        provider_cfg,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    assert transcriber.func is asr._transcribe_live_audio_wyoming

    # Gemini uses generic transcriber with transcribe_audio_gemini
    provider_cfg.asr_provider = "gemini"
    transcriber = asr.create_transcriber(
        provider_cfg,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    assert transcriber.func is asr._transcribe_live_audio_buffered
    assert transcriber.keywords["transcribe_fn"] is transcribe_audio_gemini


def test_create_recorded_audio_transcriber():
    """Test that the correct recorded audio transcriber is returned."""
    provider_cfg = MagicMock()
    provider_cfg.asr_provider = "openai"
    transcriber = asr.create_recorded_audio_transcriber(provider_cfg)
    assert transcriber is asr.transcribe_audio_openai

    provider_cfg.asr_provider = "wyoming"
    transcriber = asr.create_recorded_audio_transcriber(provider_cfg)
    assert transcriber is asr._transcribe_recorded_audio_wyoming

    provider_cfg.asr_provider = "gemini"
    transcriber = asr.create_recorded_audio_transcriber(provider_cfg)
    assert transcriber is asr.transcribe_audio_gemini


@pytest.mark.asyncio
@patch("agent_cli.services.asr.wyoming_client_context", side_effect=ConnectionRefusedError)
async def test_transcribe_recorded_audio_wyoming_connection_error(
    mock_wyoming_client_context: MagicMock,
):
    """Test that transcribe_recorded_audio_wyoming handles ConnectionRefusedError."""
    result = await asr._transcribe_recorded_audio_wyoming(
        audio_data=b"test",
        wyoming_asr_cfg=MagicMock(),
        logger=MagicMock(),
    )
    assert result == ""
    mock_wyoming_client_context.assert_called_once()


@pytest.mark.asyncio
@patch("google.genai.Client")
async def test_transcribe_audio_gemini_success(mock_client_class: MagicMock):
    """Test that transcribe_audio_gemini calls the Gemini API correctly."""
    # Setup mock client and response
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = "  hello world  "  # With whitespace to test strip()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key="test-key",
    )

    # Test with WAV data (starts with RIFF header)
    wav_data = b"RIFF\x00\x00\x00\x00WAVEfmt test audio data"
    with patch("google.genai.types.Part"):
        result = await transcribe_audio_gemini(
            audio_data=wav_data,
            gemini_asr_cfg=gemini_asr_cfg,
            logger=MagicMock(),
        )

    assert result == "hello world"  # Should be stripped
    mock_client_class.assert_called_once_with(api_key="test-key")
    mock_client.aio.models.generate_content.assert_called_once()

    # Verify the model parameter
    call_args = mock_client.aio.models.generate_content.call_args
    assert call_args.kwargs["model"] == "gemini-2.0-flash"


@pytest.mark.asyncio
@patch("google.genai.Client")
@patch("google.genai.types.Part")
async def test_transcribe_audio_gemini_converts_pcm_to_wav(
    mock_part: MagicMock,
    mock_client_class: MagicMock,
):
    """Test that transcribe_audio_gemini auto-converts PCM to WAV."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = "transcribed text"
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key="test-key",
    )

    # Test with raw PCM data (no RIFF header)
    pcm_data = b"\x00\x00\x01\x00" * 100
    result = await transcribe_audio_gemini(
        audio_data=pcm_data,
        gemini_asr_cfg=gemini_asr_cfg,
        logger=MagicMock(),
    )

    assert result == "transcribed text"

    # Verify the audio was converted to WAV (check the Part.from_bytes call)
    audio_part_call = mock_part.from_bytes.call_args
    assert audio_part_call.kwargs["mime_type"] == "audio/wav"
    # The data should now be WAV format (starts with RIFF)
    assert audio_part_call.kwargs["data"][:4] == b"RIFF"


@pytest.mark.asyncio
async def test_transcribe_audio_gemini_missing_api_key():
    """Test that transcribe_audio_gemini raises error when API key is missing."""
    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key=None,
    )

    with pytest.raises(ValueError, match="Gemini API key is not set"):
        await transcribe_audio_gemini(
            audio_data=b"test audio",
            gemini_asr_cfg=gemini_asr_cfg,
            logger=MagicMock(),
        )
