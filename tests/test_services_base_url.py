"""Tests for custom base URL support in services."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.services import synthesize_speech_openai


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
