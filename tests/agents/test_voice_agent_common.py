"""Tests for the voice_agent_common module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.agents._voice_agent_common import (
    get_instruction_from_audio,
    process_instruction_and_respond,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.mark.asyncio
@patch("agent_cli.agents._voice_agent_common.get_asr_service")
async def test_get_instruction_from_audio(mock_get_asr_service: MagicMock) -> None:
    """Test the get_instruction_from_audio function."""
    mock_asr_service = AsyncMock()
    mock_asr_service.transcribe.return_value = "test instruction"
    mock_get_asr_service.return_value = mock_asr_service
    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="localhost", wyoming_asr_port=1234)
    openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")

    result = await get_instruction_from_audio(
        audio_data=b"test audio",
        provider_config=provider_cfg,
        wyoming_asr_config=wyoming_asr_cfg,
        openai_asr_config=openai_asr_cfg,
        quiet=False,
        logger=MagicMock(),
    )
    assert result == "test instruction"
    mock_get_asr_service.assert_called_once()
    mock_asr_service.transcribe.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.agents._voice_agent_common.get_asr_service")
async def test_get_instruction_from_audio_error(mock_get_asr_service: MagicMock) -> None:
    """Test the get_instruction_from_audio function when an error occurs."""
    mock_asr_service = AsyncMock()
    mock_asr_service.transcribe.side_effect = Exception("test error")
    mock_get_asr_service.return_value = mock_asr_service
    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="localhost", wyoming_asr_port=1234)
    openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")

    result = await get_instruction_from_audio(
        audio_data=b"test audio",
        provider_config=provider_cfg,
        wyoming_asr_config=wyoming_asr_cfg,
        openai_asr_config=openai_asr_cfg,
        quiet=False,
        logger=MagicMock(),
    )
    assert result is None
    mock_get_asr_service.assert_called_once()
    mock_asr_service.transcribe.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.agents._voice_agent_common.handle_tts_playback")
@patch("agent_cli.agents._voice_agent_common.get_llm_service")
async def test_process_instruction_and_respond(
    mock_get_llm_service: MagicMock,
    mock_handle_tts_playback: MagicMock,
) -> None:
    """Test the process_instruction_and_respond function."""
    general_cfg = config.General(
        log_level="INFO",
        log_file=None,
        list_devices=False,
        quiet=False,
        clipboard=True,
    )
    provider_cfg = config.ProviderSelection(
        llm_provider="local",
        tts_provider="local",
        asr_provider="local",
    )
    ollama_cfg = config.Ollama(ollama_model="test-model", ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4")
    audio_out_cfg = config.AudioOutput(enable_tts=True, output_device_index=1)
    wyoming_tts_cfg = config.WyomingTTS(
        wyoming_tts_ip="localhost",
        wyoming_tts_port=5678,
        wyoming_voice="test-voice",
    )
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")

    mock_llm_service = MagicMock()

    async def mock_chat_generator() -> AsyncGenerator[str, None]:
        yield "Corrected text"

    mock_llm_service.chat.return_value = mock_chat_generator()
    mock_get_llm_service.return_value = mock_llm_service

    with (
        patch(
            "agent_cli.agents._voice_agent_common.pyperclip.paste",
            return_value="Corrected text",
        ),
        patch("agent_cli.agents._voice_agent_common.pyperclip.copy"),
    ):
        await process_instruction_and_respond(
            instruction="test instruction",
            original_text="original text",
            provider_config=provider_cfg,
            general_config=general_cfg,
            ollama_config=ollama_cfg,
            openai_llm_config=openai_llm_cfg,
            audio_output_config=audio_out_cfg,
            wyoming_tts_config=wyoming_tts_cfg,
            openai_tts_config=openai_tts_cfg,
            system_prompt="system prompt",
            agent_instructions="agent instructions",
            live=MagicMock(),
            logger=MagicMock(),
        )
    mock_get_llm_service.assert_called_once()
    mock_llm_service.chat.assert_called_once()
    mock_handle_tts_playback.assert_called_once()
