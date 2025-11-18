"""Extra tests for the TTS common module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.services.tts import _save_audio_file, handle_tts_playback


@pytest.mark.asyncio
@patch("agent_cli.services.tts.asyncio.to_thread")
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


@pytest.mark.asyncio
@patch("agent_cli.services.tts._speak_text", new_callable=AsyncMock)
async def test_handle_tts_playback_os_error(mock_speak_text: AsyncMock) -> None:
    """Test handle_tts_playback with OSError."""
    mock_speak_text.side_effect = OSError("Connection error")
    mock_live = MagicMock()

    provider_cfg = config.ProviderSelection(
        tts_provider="wyoming",
        asr_provider="wyoming",
        llm_provider="ollama",
    )
    audio_out_cfg = config.AudioOutput(enable_tts=True)
    wyoming_tts_cfg = config.WyomingTTS(tts_wyoming_ip="localhost", tts_wyoming_port=1234)
    openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
    kokoro_tts_cfg = config.KokoroTTS(
        tts_kokoro_model="tts-1",
        tts_kokoro_voice="alloy",
        tts_kokoro_host="http://localhost:8000/v1",
    )

    result = await handle_tts_playback(
        text="hello",
        provider_cfg=provider_cfg,
        audio_output_cfg=audio_out_cfg,
        wyoming_tts_cfg=wyoming_tts_cfg,
        openai_tts_cfg=openai_tts_cfg,
        kokoro_tts_cfg=kokoro_tts_cfg,
        save_file=None,
        quiet=False,
        logger=MagicMock(),
        live=mock_live,
    )

    assert result is None
