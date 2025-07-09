"""Tests for the TTS common module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.tts import handle_tts_playback

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
@patch("agent_cli.tts._speak_text", new_callable=AsyncMock)
async def test_handle_tts_playback(mock_speak_text: AsyncMock) -> None:
    """Test the handle_tts_playback function."""
    mock_speak_text.return_value = b"audio data"
    mock_live = MagicMock()
    provider_cfg = config.ProviderSelection(
        tts_provider="local",
        asr_provider="local",
        llm_provider="local",
    )
    audio_out_cfg = config.AudioOutput(enable_tts=True, output_device_index=1)
    wyoming_tts_cfg = config.WyomingTTS(
        wyoming_tts_ip="localhost",
        wyoming_tts_port=1234,
        wyoming_voice="test-voice",
    )
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")
    openai_llm_cfg = config.OpenAILLM(
        openai_llm_model="gpt-4o-mini",
        openai_api_key="fake-key",
    )

    await handle_tts_playback(
        text="hello",
        provider_config=provider_cfg,
        audio_output_config=audio_out_cfg,
        wyoming_tts_config=wyoming_tts_cfg,
        openai_tts_config=openai_tts_cfg,
        openai_llm_config=openai_llm_cfg,
        save_file=None,
        quiet=False,
        logger=MagicMock(),
        play_audio=True,
        live=mock_live,
    )

    mock_speak_text.assert_called_once_with(
        text="hello",
        provider_config=provider_cfg,
        audio_output_config=audio_out_cfg,
        wyoming_tts_config=wyoming_tts_cfg,
        openai_tts_config=openai_tts_cfg,
        openai_llm_config=mock_speak_text.call_args.kwargs["openai_llm_config"],
        logger=mock_speak_text.call_args.kwargs["logger"],
        quiet=False,
        play_audio_flag=True,
        stop_event=None,
        live=mock_live,
    )


@pytest.mark.asyncio
@patch("agent_cli.tts._speak_text", new_callable=AsyncMock)
async def test_handle_tts_playback_with_save_file(
    mock_speak_text: AsyncMock,
    tmp_path: Path,
) -> None:
    """Test the handle_tts_playback function with file saving."""
    mock_speak_text.return_value = b"audio data"
    save_file = tmp_path / "test.wav"
    mock_live = MagicMock()

    provider_cfg = config.ProviderSelection(
        tts_provider="local",
        asr_provider="local",
        llm_provider="local",
    )
    audio_out_cfg = config.AudioOutput(enable_tts=True, output_device_index=1)
    wyoming_tts_cfg = config.WyomingTTS(
        wyoming_tts_ip="localhost",
        wyoming_tts_port=1234,
        wyoming_voice="test-voice",
    )
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")
    openai_llm_cfg = config.OpenAILLM(
        openai_llm_model="gpt-4o-mini",
        openai_api_key="fake-key",
    )

    await handle_tts_playback(
        text="hello",
        provider_config=provider_cfg,
        audio_output_config=audio_out_cfg,
        wyoming_tts_config=wyoming_tts_cfg,
        openai_tts_config=openai_tts_cfg,
        openai_llm_config=openai_llm_cfg,
        save_file=save_file,
        quiet=False,
        logger=MagicMock(),
        play_audio=True,
        live=mock_live,
    )

    # Verify the file was saved
    assert save_file.exists()
    assert save_file.read_bytes() == b"audio data"


@pytest.mark.asyncio
@patch("agent_cli.tts._speak_text", new_callable=AsyncMock)
async def test_handle_tts_playback_no_audio(mock_speak_text: AsyncMock) -> None:
    """Test the handle_tts_playback function when no audio is returned."""
    mock_speak_text.return_value = None
    mock_live = MagicMock()
    provider_cfg = config.ProviderSelection(
        tts_provider="local",
        asr_provider="local",
        llm_provider="local",
    )
    audio_out_cfg = config.AudioOutput(enable_tts=True, output_device_index=1)
    wyoming_tts_cfg = config.WyomingTTS(
        wyoming_tts_ip="localhost",
        wyoming_tts_port=1234,
        wyoming_voice="test-voice",
    )
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")
    openai_llm_cfg = config.OpenAILLM(
        openai_llm_model="gpt-4o-mini",
        openai_api_key="fake-key",
    )

    await handle_tts_playback(
        text="hello",
        provider_config=provider_cfg,
        audio_output_config=audio_out_cfg,
        wyoming_tts_config=wyoming_tts_cfg,
        openai_tts_config=openai_tts_cfg,
        openai_llm_config=openai_llm_cfg,
        save_file=None,
        quiet=False,
        logger=MagicMock(),
        play_audio=True,
        live=mock_live,
    )

    mock_speak_text.assert_called_once()
