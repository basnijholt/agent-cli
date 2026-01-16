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
@patch("agent_cli.agents._voice_agent_common.asr.create_recorded_audio_transcriber")
async def test_get_instruction_from_audio(mock_create_transcriber: MagicMock) -> None:
    """Test the get_instruction_from_audio function."""
    mock_transcriber = AsyncMock(return_value="test instruction")
    mock_create_transcriber.return_value = mock_transcriber
    provider_cfg = config.ProviderSelection(
        asr_provider="wyoming",
        llm_provider="ollama",
        tts_provider="wyoming",
    )
    audio_in_cfg = config.AudioInput(input_device_index=1)
    wyoming_asr_cfg = config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=1234)
    openai_asr_cfg = config.OpenAIASR(asr_openai_model="whisper-1")
    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key="test-key",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test-model", llm_ollama_host="localhost")

    result = await get_instruction_from_audio(
        audio_data=b"test audio",
        provider_cfg=provider_cfg,
        audio_input_cfg=audio_in_cfg,
        wyoming_asr_cfg=wyoming_asr_cfg,
        openai_asr_cfg=openai_asr_cfg,
        gemini_asr_cfg=gemini_asr_cfg,
        ollama_cfg=ollama_cfg,
        logger=MagicMock(),
        quiet=False,
    )
    assert result == "test instruction"
    mock_create_transcriber.assert_called_once()
    mock_transcriber.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.agents._voice_agent_common.asr.create_recorded_audio_transcriber")
async def test_get_instruction_from_audio_error(mock_create_transcriber: MagicMock) -> None:
    """Test the get_instruction_from_audio function when an error occurs."""
    mock_transcriber = AsyncMock(side_effect=Exception("test error"))
    mock_create_transcriber.return_value = mock_transcriber
    provider_cfg = config.ProviderSelection(
        asr_provider="wyoming",
        llm_provider="ollama",
        tts_provider="wyoming",
    )
    audio_in_cfg = config.AudioInput(input_device_index=1)
    wyoming_asr_cfg = config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=1234)
    openai_asr_cfg = config.OpenAIASR(asr_openai_model="whisper-1")
    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key="test-key",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test-model", llm_ollama_host="localhost")

    result = await get_instruction_from_audio(
        audio_data=b"test audio",
        provider_cfg=provider_cfg,
        audio_input_cfg=audio_in_cfg,
        wyoming_asr_cfg=wyoming_asr_cfg,
        openai_asr_cfg=openai_asr_cfg,
        gemini_asr_cfg=gemini_asr_cfg,
        ollama_cfg=ollama_cfg,
        logger=MagicMock(),
        quiet=False,
    )
    assert result is None
    mock_create_transcriber.assert_called_once()
    mock_transcriber.assert_called_once()


@pytest.mark.asyncio
@patch("agent_cli.agents._voice_agent_common.process_and_update_clipboard")
@patch("agent_cli.agents._voice_agent_common.handle_tts_playback")
async def test_process_instruction_and_respond(
    mock_handle_tts_playback: MagicMock,
    mock_process_and_update_clipboard: MagicMock,
) -> None:
    """Test the process_instruction_and_respond function."""
    # Mock the LLM to return a result
    mock_process_and_update_clipboard.return_value = "processed text"

    general_cfg = config.General(
        log_level="INFO",
        log_file=None,
        list_devices=False,
        quiet=False,
        clipboard=True,
    )
    provider_cfg = config.ProviderSelection(
        llm_provider="ollama",
        tts_provider="wyoming",
        asr_provider="wyoming",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test-model", llm_ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(llm_openai_model="gpt-4", openai_base_url=None)
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )
    audio_out_cfg = config.AudioOutput(enable_tts=True, output_device_index=1)
    wyoming_tts_cfg = config.WyomingTTS(
        tts_wyoming_ip="localhost",
        tts_wyoming_port=5678,
        tts_wyoming_voice="test-voice",
    )
    openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
    kokoro_tts_cfg = config.KokoroTTS(
        tts_kokoro_model="tts-1",
        tts_kokoro_voice="alloy",
        tts_kokoro_host="http://localhost:8000/v1",
    )

    result = await process_instruction_and_respond(
        instruction="test instruction",
        original_text="original text",
        provider_cfg=provider_cfg,
        general_cfg=general_cfg,
        ollama_cfg=ollama_cfg,
        openai_llm_cfg=openai_llm_cfg,
        gemini_llm_cfg=gemini_llm_cfg,
        audio_output_cfg=audio_out_cfg,
        wyoming_tts_cfg=wyoming_tts_cfg,
        openai_tts_cfg=openai_tts_cfg,
        kokoro_tts_cfg=kokoro_tts_cfg,
        system_prompt="system prompt",
        agent_instructions="agent instructions",
        live=MagicMock(),
        logger=MagicMock(),
    )
    assert result == "processed text"
    mock_process_and_update_clipboard.assert_called_once()
    mock_handle_tts_playback.assert_called_once()
