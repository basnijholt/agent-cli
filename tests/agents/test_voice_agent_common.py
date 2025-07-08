"""Tests for the voice_agent_common module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.agents._config import (
    ASRConfig,
    FileConfig,
    GeneralConfig,
    LLMConfig,
    TTSConfig,
)
from agent_cli.agents._voice_agent_common import (
    get_instruction_from_audio,
    process_instruction_and_respond,
)


@pytest.mark.asyncio
@patch("agent_cli.agents._voice_agent_common.asr.get_recorded_audio_transcriber")
async def test_get_instruction_from_audio(mock_get_transcriber: MagicMock) -> None:
    """Test the get_instruction_from_audio function."""
    mock_transcriber = AsyncMock(return_value="test instruction")
    mock_get_transcriber.return_value = mock_transcriber
    asr_config = ASRConfig(
        server_ip="localhost",
        server_port=1234,
        input_device_index=1,
        input_device_name=None,
    )
    result = await get_instruction_from_audio(
        b"test audio",
        asr_config,
        MagicMock(),
        quiet=False,
    )
    assert result == "test instruction"
    mock_get_transcriber.assert_called_once()
    mock_transcriber.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.agents._voice_agent_common.process_and_update_clipboard")
@patch("agent_cli.agents._voice_agent_common.handle_tts_playback")
async def test_process_instruction_and_respond(
    mock_handle_tts_playback: MagicMock,
    mock_process_and_update_clipboard: MagicMock,
) -> None:
    """Test the process_instruction_and_respond function."""
    general_cfg = GeneralConfig(
        log_level="INFO",
        log_file=None,
        list_devices=False,
        quiet=False,
        clipboard=True,
    )
    llm_config = LLMConfig(
        model="test-model",
        ollama_host="localhost",
        service_provider="local",
        openai_api_key=None,
    )
    tts_config = TTSConfig(
        enabled=True,
        server_ip="localhost",
        server_port=5678,
        voice_name="test-voice",
        language="en",
        speaker=None,
        output_device_index=1,
        output_device_name=None,
        speed=1.0,
    )
    file_config = FileConfig(save_file=None, history_dir=None)
    with patch("agent_cli.agents.autocorrect.pyperclip.copy"):
        await process_instruction_and_respond(
            "test instruction",
            "original text",
            general_cfg,
            llm_config,
            tts_config,
            file_config,
            "system prompt",
            "agent instructions",
            1,
            MagicMock(),
            MagicMock(),
        )
    mock_process_and_update_clipboard.assert_called_once()
    mock_handle_tts_playback.assert_called_once()
