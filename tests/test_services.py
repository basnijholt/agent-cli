"""Tests for the services module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import asr, tts
from agent_cli.agents._config import (
    ASRConfig,
    OpenAIASRConfig,
    OpenAITTSConfig,
    TTSConfig,
    WyomingASRConfig,
    WyomingTTSConfig,
)
from agent_cli.services import synthesize_speech_openai, transcribe_audio_openai


@pytest.mark.asyncio
@patch("agent_cli.services._get_openai_client")
async def test_transcribe_audio_openai(mock_openai_client: MagicMock) -> None:
    """Test the transcribe_audio_openai function."""
    mock_audio = b"test audio"
    mock_api_key = "test_api_key"
    mock_logger = MagicMock()
    mock_client_instance = mock_openai_client.return_value
    mock_transcription = MagicMock()
    mock_transcription.text = "test transcription"
    mock_client_instance.audio.transcriptions.create = AsyncMock(
        return_value=mock_transcription,
    )

    result = await transcribe_audio_openai(mock_audio, mock_api_key, mock_logger)

    assert result == "test transcription"
    mock_openai_client.assert_called_once_with(api_key=mock_api_key)
    mock_client_instance.audio.transcriptions.create.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.services._get_openai_client")
async def test_synthesize_speech_openai(mock_openai_client: MagicMock) -> None:
    """Test the synthesize_speech_openai function."""
    mock_text = "test text"
    mock_api_key = "test_api_key"
    mock_logger = MagicMock()
    mock_client_instance = mock_openai_client.return_value
    mock_response = MagicMock()
    mock_response.content = b"test audio"
    mock_client_instance.audio.speech.create = AsyncMock(return_value=mock_response)

    result = await synthesize_speech_openai(mock_text, mock_api_key, mock_logger)

    assert result == b"test audio"
    mock_openai_client.assert_called_once_with(api_key=mock_api_key)
    mock_client_instance.audio.speech.create.assert_called_once_with(
        model="tts-1",
        voice="alloy",
        input=mock_text,
        response_format="wav",
    )


def test_get_transcriber_wyoming() -> None:
    """Test that get_transcriber returns the Wyoming transcriber."""
    asr_config = ASRConfig(
        provider="local",
        input_device_index=None,
        input_device_name=None,
        local=WyomingASRConfig(server_ip="localhost", server_port=1234),
        openai=OpenAIASRConfig(api_key=None, model="whisper-1"),
    )
    transcriber = asr.get_transcriber(asr_config)
    assert transcriber == asr.transcribe_live_audio_wyoming


def test_get_synthesizer_wyoming() -> None:
    """Test that get_synthesizer returns the Wyoming synthesizer."""
    tts_config = TTSConfig(
        enabled=True,
        provider="local",
        output_device_index=None,
        output_device_name=None,
        speed=1.0,
        local=WyomingTTSConfig(
            server_ip="localhost",
            server_port=1234,
            voice_name=None,
            language=None,
            speaker=None,
        ),
        openai=OpenAITTSConfig(api_key=None, model="tts-1", voice="alloy"),
    )
    synthesizer = tts.get_synthesizer(tts_config)
    assert synthesizer == tts._synthesize_speech_wyoming
