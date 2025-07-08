"""Tests for the services module."""

from __future__ import annotations

import functools
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import asr, tts
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


def test_get_transcriber_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that get_transcriber returns the OpenAI transcriber."""
    monkeypatch.setattr("agent_cli.config.SERVICE_PROVIDER", "openai")
    monkeypatch.setattr("agent_cli.config.OPENAI_API_KEY", "test_api_key")
    transcriber = asr.get_transcriber()
    assert isinstance(transcriber, functools.partial)
    assert "transcribe_live_audio_openai" in transcriber.func.__name__


def test_get_transcriber_wyoming(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that get_transcriber returns the Wyoming transcriber."""
    monkeypatch.setattr("agent_cli.config.SERVICE_PROVIDER", "local")
    transcriber = asr.get_transcriber()
    assert transcriber == asr.transcribe_live_audio_wyoming


def test_get_synthesizer_wyoming() -> None:
    """Test that get_synthesizer returns the Wyoming synthesizer."""
    synthesizer = tts.get_synthesizer(service_provider="local", openai_api_key=None)
    assert synthesizer == tts._synthesize_speech_wyoming
