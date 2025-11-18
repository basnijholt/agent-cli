"""Tests for the services module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.services import asr, synthesize_speech_openai, transcribe_audio_openai, tts


@pytest.mark.asyncio
@patch("agent_cli.services._get_openai_client")
async def test_transcribe_audio_openai(mock_openai_client: MagicMock) -> None:
    """Test the transcribe_audio_openai function."""
    mock_audio = b"test audio"
    mock_logger = MagicMock()
    mock_client_instance = mock_openai_client.return_value
    mock_transcription = MagicMock()
    mock_transcription.text = "test transcription"
    mock_client_instance.audio.transcriptions.create = AsyncMock(
        return_value=mock_transcription,
    )
    openai_asr_cfg = config.OpenAIASR(
        asr_openai_model="whisper-1",
        openai_api_key="test_api_key",
    )

    result = await transcribe_audio_openai(mock_audio, openai_asr_cfg, mock_logger)

    assert result == "test transcription"
    mock_openai_client.assert_called_once_with(api_key="test_api_key", base_url=None)
    mock_client_instance.audio.transcriptions.create.assert_called_once_with(
        model="whisper-1",
        file=mock_client_instance.audio.transcriptions.create.call_args[1]["file"],
    )


@pytest.mark.asyncio
@patch("agent_cli.services._get_openai_client")
async def test_synthesize_speech_openai(mock_openai_client: MagicMock) -> None:
    """Test the synthesize_speech_openai function."""
    mock_text = "test text"
    mock_logger = MagicMock()
    mock_client_instance = mock_openai_client.return_value
    mock_response = MagicMock()
    mock_response.content = b"test audio"
    mock_client_instance.audio.speech.create = AsyncMock(return_value=mock_response)
    openai_tts_cfg = config.OpenAITTS(
        tts_openai_model="tts-1",
        tts_openai_voice="alloy",
        openai_api_key="test_api_key",
    )

    result = await synthesize_speech_openai(mock_text, openai_tts_cfg, mock_logger)

    assert result == b"test audio"
    mock_openai_client.assert_called_once_with(api_key="test_api_key", base_url=None)
    mock_client_instance.audio.speech.create.assert_called_once_with(
        model="tts-1",
        voice="alloy",
        input=mock_text,
        response_format="wav",
    )


def test_create_transcriber_wyoming() -> None:
    """Test that create_transcriber returns the Wyoming transcriber."""
    provider_cfg = config.ProviderSelection(
        asr_provider="wyoming",
        llm_provider="ollama",
        tts_provider="wyoming",
    )
    audio_input_cfg = config.AudioInput()
    wyoming_asr_cfg = config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=1234)
    openai_asr_cfg = config.OpenAIASR(asr_openai_model="whisper-1", openai_api_key="fake-key")

    transcriber = asr.create_transcriber(
        provider_cfg,
        audio_input_cfg,
        wyoming_asr_cfg,
        openai_asr_cfg,
    )
    assert transcriber.func == asr._transcribe_live_audio_wyoming  # type: ignore[attr-defined]


def test_create_synthesizer_wyoming() -> None:
    """Test that create_synthesizer returns the Wyoming synthesizer."""
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
    synthesizer = tts.create_synthesizer(
        provider_cfg,
        audio_output_cfg,
        wyoming_tts_cfg,
        openai_tts_cfg,
        kokoro_tts_cfg,
    )
    assert synthesizer.func == tts._synthesize_speech_wyoming  # type: ignore[attr-defined]


def test_create_synthesizer_kokoro() -> None:
    """Test that create_synthesizer returns the Kokoro synthesizer."""
    provider_cfg = config.ProviderSelection(
        asr_provider="wyoming",
        llm_provider="ollama",
        tts_provider="kokoro",
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
    synthesizer = tts.create_synthesizer(
        provider_cfg,
        audio_output_cfg,
        wyoming_tts_cfg,
        openai_tts_cfg,
        kokoro_tts_cfg,
    )
    assert synthesizer.func == tts._synthesize_speech_kokoro  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_transcribe_audio_openai_no_key():
    """Test that transcribe_audio_openai fails without an API key."""
    with pytest.raises(ValueError, match="OpenAI API key is not set"):
        await transcribe_audio_openai(
            b"test audio",
            config.OpenAIASR(asr_openai_model="whisper-1", openai_api_key=None),
            MagicMock(),
        )


@pytest.mark.asyncio
async def test_synthesize_speech_openai_no_key():
    """Test that synthesize_speech_openai fails without an API key."""
    with pytest.raises(ValueError, match="OpenAI API key is not set"):
        await synthesize_speech_openai(
            "test text",
            config.OpenAITTS(
                tts_openai_model="tts-1",
                tts_openai_voice="alloy",
                openai_api_key=None,
            ),
            MagicMock(),
        )


@pytest.mark.asyncio
@patch("agent_cli.services._get_openai_client")
async def test_synthesize_speech_openai_custom_base_url(
    mock_openai_client: MagicMock,
) -> None:
    """Test synthesize_speech_openai with a custom base URL.

    Verifies that:
    1. The client is initialized with the base URL.
    2. No API key is required (dummy key is used/ignored).
    """
    mock_text = "test text"
    mock_logger = MagicMock()
    mock_client_instance = mock_openai_client.return_value
    mock_response = MagicMock()
    mock_response.content = b"custom url audio"
    mock_client_instance.audio.speech.create = AsyncMock(return_value=mock_response)

    # Config with base URL and NO API key
    openai_tts_cfg = config.OpenAITTS(
        tts_openai_model="tts-1",
        tts_openai_voice="alloy",
        tts_openai_base_url="http://my-custom-tts:8000/v1",
        openai_api_key=None,
    )

    result = await synthesize_speech_openai(mock_text, openai_tts_cfg, mock_logger)

    assert result == b"custom url audio"

    # Check client initialization
    # Should be called with base_url provided
    # API key might be "dummy-api-key" or whatever _get_openai_client defaults to if None passed
    mock_openai_client.assert_called_once()
    call_kwargs = mock_openai_client.call_args[1]
    assert call_kwargs["base_url"] == "http://my-custom-tts:8000/v1"
    # We expect None passed to the helper, which then handles the dummy key internally
    assert call_kwargs["api_key"] is None

    # Check that the logger info was called with the custom URL message
    mock_logger.info.assert_any_call(
        "Synthesizing speech with custom OpenAI-compatible endpoint: %s",
        "http://my-custom-tts:8000/v1",
    )


@pytest.mark.asyncio
@patch("agent_cli.services.tts.synthesize_speech_openai")
async def test_synthesize_speech_kokoro_delegates_to_openai(
    mock_synthesize_speech_openai: MagicMock,
) -> None:
    """Test that _synthesize_speech_kokoro delegates to synthesize_speech_openai."""
    mock_synthesize_speech_openai.return_value = b"kokoro audio"
    mock_logger = MagicMock()

    kokoro_tts_cfg = config.KokoroTTS(
        tts_kokoro_model="kokoro-v1",
        tts_kokoro_voice="af_bell",
        tts_kokoro_host="http://localhost:8880/v1",
    )

    result = await tts._synthesize_speech_kokoro(
        text="hello kokoro",
        kokoro_tts_cfg=kokoro_tts_cfg,
        logger=mock_logger,
    )

    assert result == b"kokoro audio"

    # Verify synthesize_speech_openai was called with mapped config
    mock_synthesize_speech_openai.assert_called_once()
    call_args = mock_synthesize_speech_openai.call_args
    assert call_args.kwargs["text"] == "hello kokoro"
    assert call_args.kwargs["logger"] == mock_logger

    openai_cfg_arg = call_args.kwargs["openai_tts_cfg"]
    assert isinstance(openai_cfg_arg, config.OpenAITTS)
    assert openai_cfg_arg.tts_openai_model == "kokoro-v1"
    assert openai_cfg_arg.tts_openai_voice == "af_bell"
    assert openai_cfg_arg.tts_openai_base_url == "http://localhost:8880/v1"
    # api_key should be optional/None since base_url is provided
    assert openai_cfg_arg.openai_api_key is None
