"""Tests for the voice_agent_common module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.agents._config import (
    ASRConfig,
    FileConfig,
    GeneralConfig,
    LLMConfig,
    OllamaLLMConfig,
    OpenAIASRConfig,
    OpenAILLMConfig,
    OpenAITTSConfig,
    TTSConfig,
    WyomingASRConfig,
    WyomingTTSConfig,
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
        provider="local",
        input_device_index=1,
        input_device_name=None,
        local=WyomingASRConfig(server_ip="localhost", server_port=1234),
        openai=OpenAIASRConfig(api_key=None, model="whisper-1"),
    )
    llm_config = LLMConfig(
        provider="local",
        local=OllamaLLMConfig(model="test-model", host="localhost"),
        openai=OpenAILLMConfig(api_key=None, model="gpt-4"),
    )
    result = await get_instruction_from_audio(
        audio_data=b"test audio",
        asr_config=asr_config,
        llm_config=llm_config,
        logger=MagicMock(),
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
        provider="local",
        local=OllamaLLMConfig(model="test-model", host="localhost"),
        openai=OpenAILLMConfig(api_key=None, model="gpt-4"),
    )
    tts_config = TTSConfig(
        enabled=True,
        provider="local",
        output_device_index=1,
        output_device_name=None,
        speed=1.0,
        local=WyomingTTSConfig(
            server_ip="localhost",
            server_port=5678,
            voice_name="test-voice",
            language="en",
            speaker=None,
        ),
        openai=OpenAITTSConfig(api_key=None, model="tts-1", voice="alloy"),
    )
    file_config = FileConfig(save_file=None, history_dir=None)
    with (
        patch("agent_cli.agents.autocorrect.pyperclip.copy"),
        patch("agent_cli.agents._voice_agent_common.pyperclip.paste"),
    ):
        await process_instruction_and_respond(
            instruction="test instruction",
            original_text="original text",
            general_cfg=general_cfg,
            llm_config=llm_config,
            tts_config=tts_config,
            file_config=file_config,
            system_prompt="system prompt",
            agent_instructions="agent instructions",
            live=MagicMock(),
            logger=MagicMock(),
        )
    mock_process_and_update_clipboard.assert_called_once()
    mock_handle_tts_playback.assert_called_once()
