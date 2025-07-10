"""Tests for the voice_agent_common module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
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
    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    audio_in_cfg = config.AudioInput(input_device_index=1)
    wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="localhost", wyoming_asr_port=1234)
    openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")
    ollama_cfg = config.Ollama(ollama_model="test-model", ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4")

    result = await get_instruction_from_audio(
        audio_data=b"test audio",
        provider_config=provider_cfg,
        audio_input_config=audio_in_cfg,
        wyoming_asr_config=wyoming_asr_cfg,
        openai_asr_config=openai_asr_cfg,
        ollama_config=ollama_cfg,
        openai_llm_config=openai_llm_cfg,
        logger=MagicMock(),
        quiet=False,
    )
    assert result == "test instruction"
    mock_get_transcriber.assert_called_once()
    mock_transcriber.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.agents._voice_agent_common.asr.get_recorded_audio_transcriber")
async def test_get_instruction_from_audio_error(mock_get_transcriber: MagicMock) -> None:
    """Test the get_instruction_from_audio function when an error occurs."""
    mock_transcriber = AsyncMock(side_effect=Exception("test error"))
    mock_get_transcriber.return_value = mock_transcriber
    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    audio_in_cfg = config.AudioInput(input_device_index=1)
    wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="localhost", wyoming_asr_port=1234)
    openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")
    ollama_cfg = config.Ollama(ollama_model="test-model", ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4")

    result = await get_instruction_from_audio(
        audio_data=b"test audio",
        provider_config=provider_cfg,
        audio_input_config=audio_in_cfg,
        wyoming_asr_config=wyoming_asr_cfg,
        openai_asr_config=openai_asr_cfg,
        ollama_config=ollama_cfg,
        openai_llm_config=openai_llm_cfg,
        logger=MagicMock(),
        quiet=False,
    )
    assert result is None
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
    kokoro_tts_cfg = config.KokoroTTS(
        kokoro_tts_model="tts-1",
        kokoro_tts_voice="alloy",
        kokoro_api_base="http://localhost:8000/v1",
    )

    with (
        patch("agent_cli.agents.autocorrect.pyperclip.copy"),
        patch("agent_cli.agents._voice_agent_common.pyperclip.paste"),
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
            kokoro_tts_config=kokoro_tts_cfg,
            system_prompt="system prompt",
            agent_instructions="agent instructions",
            live=MagicMock(),
            logger=MagicMock(),
        )
    mock_process_and_update_clipboard.assert_called_once()
    mock_handle_tts_playback.assert_called_once()
