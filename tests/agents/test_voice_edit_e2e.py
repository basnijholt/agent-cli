"""End-to-end tests for the voice assistant agent with simplified mocks."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.agents.voice_edit import (
    AGENT_INSTRUCTIONS,
    SYSTEM_PROMPT,
    _async_main,
)


def get_configs() -> tuple[
    config.ProviderSelection,
    config.General,
    config.AudioInput,
    config.WyomingASR,
    config.OpenAIASR,
    config.GeminiASR,
    config.Ollama,
    config.OpenAILLM,
    config.GeminiLLM,
    config.AudioOutput,
    config.WyomingTTS,
    config.OpenAITTS,
    config.KokoroTTS,
    config.GeminiTTS,
]:
    """Get all the necessary configs for the e2e test."""
    provider_cfg = config.ProviderSelection(
        asr_provider="wyoming",
        llm_provider="ollama",
        tts_provider="wyoming",
    )
    general_cfg = config.General(
        log_level="INFO",
        log_file=None,
        quiet=False,
        list_devices=False,
        clipboard=True,
        save_file=None,
    )
    audio_in_cfg = config.AudioInput(input_device_index=0)
    wyoming_asr_cfg = config.WyomingASR(asr_wyoming_ip="mock-asr-host", asr_wyoming_port=10300)
    openai_asr_cfg = config.OpenAIASR(asr_openai_model="whisper-1")
    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key="test-key",
    )
    ollama_cfg = config.Ollama(
        llm_ollama_model="test-model",
        llm_ollama_host="http://localhost:11434",
    )
    openai_llm_cfg = config.OpenAILLM(llm_openai_model="gpt-4", openai_base_url=None)
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )
    audio_out_cfg = config.AudioOutput(enable_tts=False)
    wyoming_tts_cfg = config.WyomingTTS(tts_wyoming_ip="mock-tts-host", tts_wyoming_port=10200)
    openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
    kokoro_tts_cfg = config.KokoroTTS(
        tts_kokoro_model="tts-1",
        tts_kokoro_voice="alloy",
        tts_kokoro_host="http://localhost:8000/v1",
    )
    gemini_tts_cfg = config.GeminiTTS(
        tts_gemini_model="gemini-2.5-flash-preview-tts",
        tts_gemini_voice="Kore",
        gemini_api_key="test-key",
    )
    return (
        provider_cfg,
        general_cfg,
        audio_in_cfg,
        wyoming_asr_cfg,
        openai_asr_cfg,
        gemini_asr_cfg,
        ollama_cfg,
        openai_llm_cfg,
        gemini_llm_cfg,
        audio_out_cfg,
        wyoming_tts_cfg,
        openai_tts_cfg,
        kokoro_tts_cfg,
        gemini_tts_cfg,
    )


@pytest.mark.asyncio
@patch("agent_cli.agents.voice_edit.process_instruction_and_respond", new_callable=AsyncMock)
@patch("agent_cli.agents.voice_edit.get_instruction_from_audio", new_callable=AsyncMock)
@patch("agent_cli.agents.voice_edit.asr.record_audio_with_manual_stop", new_callable=AsyncMock)
@patch("agent_cli.agents.voice_edit.get_clipboard_text", return_value="test clipboard text")
@patch("agent_cli.agents.voice_edit.setup_devices")
async def test_voice_edit_e2e(
    mock_setup_devices: MagicMock,
    mock_get_clipboard: MagicMock,
    mock_record_audio: AsyncMock,
    mock_get_instruction: AsyncMock,
    mock_process_instruction: AsyncMock,
) -> None:
    """Test end-to-end voice assistant functionality with simplified mocks."""
    mock_setup_devices.return_value = (0, "mock_device", None)
    mock_record_audio.return_value = b"audio data"
    mock_get_instruction.return_value = "this is a test"
    mock_process_instruction.return_value = "processed result"

    (
        provider_cfg,
        general_cfg,
        audio_in_cfg,
        wyoming_asr_cfg,
        openai_asr_cfg,
        gemini_asr_cfg,
        ollama_cfg,
        openai_llm_cfg,
        gemini_llm_cfg,
        audio_out_cfg,
        wyoming_tts_cfg,
        openai_tts_cfg,
        kokoro_tts_cfg,
        gemini_tts_cfg,
    ) = get_configs()

    # This test focuses on the main loop, so we stop it after one run
    with patch("agent_cli.agents.voice_edit.signal_handling_context") as mock_signal_context:
        mock_stop_event = MagicMock()
        mock_stop_event.is_set.return_value = False
        mock_signal_context.return_value.__enter__.return_value = mock_stop_event

        await _async_main(
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            audio_in_cfg=audio_in_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            gemini_asr_cfg=gemini_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            audio_out_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
            kokoro_tts_cfg=kokoro_tts_cfg,
            gemini_tts_cfg=gemini_tts_cfg,
        )

    # Assertions
    mock_get_clipboard.assert_called_once()
    mock_record_audio.assert_called_once()
    mock_get_instruction.assert_called_once_with(
        audio_data=b"audio data",
        provider_cfg=provider_cfg,
        audio_input_cfg=audio_in_cfg,
        wyoming_asr_cfg=wyoming_asr_cfg,
        openai_asr_cfg=openai_asr_cfg,
        gemini_asr_cfg=gemini_asr_cfg,
        ollama_cfg=ollama_cfg,
        logger=ANY,
        quiet=False,
    )
    mock_process_instruction.assert_called_once_with(
        instruction="this is a test",
        original_text="test clipboard text",
        provider_cfg=provider_cfg,
        general_cfg=general_cfg,
        ollama_cfg=ollama_cfg,
        openai_llm_cfg=openai_llm_cfg,
        gemini_llm_cfg=gemini_llm_cfg,
        audio_output_cfg=audio_out_cfg,
        wyoming_tts_cfg=wyoming_tts_cfg,
        openai_tts_cfg=openai_tts_cfg,
        kokoro_tts_cfg=kokoro_tts_cfg,
        gemini_tts_cfg=gemini_tts_cfg,
        system_prompt=SYSTEM_PROMPT,
        agent_instructions=AGENT_INSTRUCTIONS,
        live=ANY,
        logger=ANY,
    )
