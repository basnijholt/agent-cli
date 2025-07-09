"""Extra tests for the TTS common module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.agents import config
from agent_cli.agents._tts_common import _save_audio_file, handle_tts_playback


@pytest.mark.asyncio()
@patch("agent_cli.agents._tts_common.asyncio.to_thread")
async def test_save_audio_file_os_error(mock_to_thread: AsyncMock) -> None:
    """Test _save_audio_file with OSError."""
    mock_to_thread.side_effect = OSError("Permission denied")

    await _save_audio_file(
        b"audio data",
        Path("test.wav"),
        quiet=False,
        logger=MagicMock(),
    )

    mock_to_thread.assert_called_once()


@pytest.mark.asyncio()
@patch("agent_cli.agents._tts_common.tts.speak_text", new_callable=AsyncMock)
async def test_handle_tts_playback_os_error(mock_speak_text: AsyncMock) -> None:
    """Test handle_tts_playback with OSError."""
    mock_speak_text.side_effect = OSError("Connection error")
    mock_live = MagicMock()

    provider_cfg = config.ProviderSelection(
        tts_provider="local",
        asr_provider="local",
        llm_provider="local",
    )
    audio_out_cfg = config.AudioOutput(enable_tts=True)
    wyoming_tts_cfg = config.WyomingTTS(wyoming_tts_ip="localhost", wyoming_tts_port=1234)
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")
    openai_llm_cfg = config.OpenAILLM(
        openai_llm_model="gpt-4o-mini",
        openai_api_key="fake-key",
    )

    result = await handle_tts_playback(
        text="hello",
        provider_config=provider_cfg,
        audio_output_config=audio_out_cfg,
        wyoming_tts_config=wyoming_tts_cfg,
        openai_tts_config=openai_tts_cfg,
        openai_llm_config=openai_llm_cfg,
        save_file=None,
        quiet=False,
        logger=MagicMock(),
        live=mock_live,
    )

    assert result is None
