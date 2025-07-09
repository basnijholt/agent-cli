"""Tests for the services module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pydantic
import pytest

from agent_cli import config
from agent_cli.services import tts
from agent_cli.services.factory import get_asr_service
from agent_cli.services.local.asr import WyomingASRService
from agent_cli.services.openai.asr import OpenAIASRService
from agent_cli.services.openai.tts import OpenAITTSService


@pytest.mark.asyncio
@patch("agent_cli.services.openai.asr.AsyncOpenAI")
async def test_transcribe_audio_openai(mock_openai_client: MagicMock) -> None:
    """Test the transcribe_audio_openai function."""
    mock_audio = b"test audio"
    mock_client_instance = mock_openai_client.return_value
    mock_transcription = MagicMock()
    mock_transcription.text = "test transcription"
    mock_client_instance.audio.transcriptions.create = AsyncMock(
        return_value=mock_transcription,
    )
    openai_asr_config = config.OpenAIASR(
        openai_asr_model="whisper-1",
        api_key="test_key",
    )
    service = OpenAIASRService(
        openai_asr_config=openai_asr_config,
        is_interactive=False,
    )

    result = await service.transcribe(
        mock_audio,
    )

    assert result == "test transcription"


@pytest.mark.asyncio
@patch("agent_cli.services.openai.tts.AsyncOpenAI")
async def test_synthesize_speech_openai(mock_openai_client: MagicMock) -> None:
    """Test the synthesize_speech_openai function."""
    mock_text = "test text"
    mock_client_instance = mock_openai_client.return_value
    mock_response = MagicMock()
    mock_response.content = b"test audio"
    mock_client_instance.audio.speech.create = AsyncMock(return_value=mock_response)
    openai_tts_config = config.OpenAITTS(
        openai_tts_model="tts-1",
        openai_tts_voice="alloy",
        openai_api_key="test_key",
    )
    service = OpenAITTSService(
        openai_tts_config=openai_tts_config,
        is_interactive=False,
    )

    result = await service.synthesise(
        text=mock_text,
    )

    assert result == b"test audio"


def test_get_transcriber_wyoming() -> None:
    """Test that get_transcriber returns the Wyoming transcriber."""
    provider_config = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    wyoming_asr_config = config.WyomingASR(wyoming_asr_ip="localhost", wyoming_asr_port=1234)
    openai_asr_config = config.OpenAIASR(openai_asr_model="whisper-1")
    transcriber = get_asr_service(
        provider_config,
        wyoming_asr_config,
        openai_asr_config,
        is_interactive=False,
    )
    assert isinstance(transcriber, WyomingASRService)


def test_get_synthesizer_wyoming() -> None:
    """Test that get_synthesizer returns the Wyoming synthesizer."""
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
    synthesizer = tts.get_synthesizer(
        provider_config,
        audio_output_config,
        wyoming_tts_config,
        openai_tts_config,
        openai_llm_config,
    )
    assert synthesizer.func.__name__ == "_synthesize_speech_wyoming"


@pytest.mark.asyncio
async def test_transcribe_audio_openai_no_key():
    """Test that transcribe_audio_openai fails without an API key."""
    service = OpenAIASRService(
        openai_asr_config=config.OpenAIASR(openai_asr_model="whisper-1"),
        is_interactive=False,
    )
    await service.transcribe(b"test audio")


@pytest.mark.asyncio
async def test_synthesize_speech_openai_no_key():
    """Test that synthesize_speech_openai fails without an API key."""
    service = OpenAITTSService(
        openai_tts_config=config.OpenAITTS(
            openai_tts_model="tts-1",
            openai_tts_voice="alloy",
        ),
        is_interactive=False,
    )
    await service.synthesise("test text")


def test_get_transcriber_unsupported():
    """Test that get_transcriber raises an error for unsupported providers."""
    with pytest.raises(pydantic.ValidationError):
        get_asr_service(
            config.ProviderSelection(
                asr_provider="unsupported",
                llm_provider="local",
                tts_provider="local",
            ),
            MagicMock(),
            MagicMock(),
        )


def test_get_synthesizer_unsupported():
    """Test that get_synthesizer returns a dummy for unsupported providers."""
    with pytest.raises(pydantic.ValidationError):
        tts.get_synthesizer(
            config.ProviderSelection(
                asr_provider="local",
                llm_provider="local",
                tts_provider="unsupported",
            ),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
