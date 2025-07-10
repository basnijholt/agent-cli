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
from tests.mocks.audio import MockPyAudio


def get_configs() -> tuple[
    config.ProviderSelection,
    config.General,
    config.AudioInput,
    config.WyomingASR,
    config.OpenAIASR,
    config.Ollama,
    config.OpenAILLM,
    config.AudioOutput,
    config.WyomingTTS,
    config.OpenAITTS,
    config.KokoroTTS,
]:
    """Get all the necessary configs for the e2e test."""
    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
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
    wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="mock-asr-host", wyoming_asr_port=10300)
    openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")
    ollama_cfg = config.Ollama(ollama_model="test-model", ollama_host="http://localhost:11434")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4")
    audio_out_cfg = config.AudioOutput(enable_tts=False)
    wyoming_tts_cfg = config.WyomingTTS(wyoming_tts_ip="mock-tts-host", wyoming_tts_port=10200)
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")
    kokoro_tts_cfg = config.KokoroTTS(
        kokoro_tts_model="tts-1",
        kokoro_tts_voice="alloy",
        kokoro_tts_host="http://localhost:8000/v1",
    )
    return (
        provider_cfg,
        general_cfg,
        audio_in_cfg,
        wyoming_asr_cfg,
        openai_asr_cfg,
        ollama_cfg,
        openai_llm_cfg,
        audio_out_cfg,
        wyoming_tts_cfg,
        openai_tts_cfg,
        kokoro_tts_cfg,
    )


@pytest.mark.asyncio
@patch("agent_cli.agents.voice_edit.process_instruction_and_respond", new_callable=AsyncMock)
@patch("agent_cli.agents.voice_edit.get_instruction_from_audio", new_callable=AsyncMock)
@patch("agent_cli.agents.voice_edit.asr.record_audio_with_manual_stop", new_callable=AsyncMock)
@patch("agent_cli.agents.voice_edit.get_clipboard_text", return_value="test clipboard text")
@patch("agent_cli.agents.voice_edit.setup_devices")
@patch("agent_cli.agents.voice_edit.pyaudio_context")
async def test_voice_edit_e2e(
    mock_pyaudio_context: MagicMock,
    mock_setup_devices: MagicMock,
    mock_get_clipboard: MagicMock,
    mock_record_audio: AsyncMock,
    mock_get_instruction: AsyncMock,
    mock_process_instruction: AsyncMock,
) -> None:
    """Test end-to-end voice assistant functionality with simplified mocks."""
    mock_pyaudio_instance = MockPyAudio(
        [{"maxInputChannels": 1, "maxOutputChannels": 0, "index": 0, "defaultSampleRate": 44100.0}],
    )
    mock_pyaudio_context.return_value.__enter__.return_value = mock_pyaudio_instance
    mock_setup_devices.return_value = (0, "mock_device", None)
    mock_record_audio.return_value = b"audio data"
    mock_get_instruction.return_value = "this is a test"

    (
        provider_cfg,
        general_cfg,
        audio_in_cfg,
        wyoming_asr_cfg,
        openai_asr_cfg,
        ollama_cfg,
        openai_llm_cfg,
        audio_out_cfg,
        wyoming_tts_cfg,
        openai_tts_cfg,
        kokoro_tts_cfg,
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
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            audio_out_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
            kokoro_tts_config=kokoro_tts_cfg,
        )

    # Assertions
    mock_get_clipboard.assert_called_once()
    mock_record_audio.assert_called_once()
    mock_get_instruction.assert_called_once_with(
        audio_data=b"audio data",
        provider_config=provider_cfg,
        audio_input_config=audio_in_cfg,
        wyoming_asr_config=wyoming_asr_cfg,
        openai_asr_config=openai_asr_cfg,
        ollama_config=ollama_cfg,
        openai_llm_config=openai_llm_cfg,
        logger=ANY,
        quiet=False,
    )
    mock_process_instruction.assert_called_once_with(
        instruction="this is a test",
        original_text="test clipboard text",
        provider_config=provider_cfg,
        general_config=general_cfg,
        ollama_config=ollama_cfg,
        openai_llm_config=openai_llm_cfg,
        audio_output_config=audio_out_cfg,
        wyoming_tts_config=wyoming_tts_cfg,
        openai_tts_config=openai_tts_cfg,
        kokoro_tts_config=kokoro_tts_cfg,
        system_prompt=SYSTEM_PROMPT,
        agent_instructions=AGENT_INSTRUCTIONS,
        live=ANY,
        logger=ANY,
    )
