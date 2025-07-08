"""End-to-end tests for the voice assistant agent with simplified mocks."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from agent_cli.agents._config import (
    ASRConfig,
    FileConfig,
    GeneralConfig,
    LLMConfig,
    TTSConfig,
)
from agent_cli.agents.voice_assistant import (
    AGENT_INSTRUCTIONS,
    SYSTEM_PROMPT,
    _async_main,
)
from tests.mocks.audio import MockPyAudio


def get_configs() -> tuple[GeneralConfig, ASRConfig, LLMConfig, TTSConfig, FileConfig]:
    """Get all the necessary configs for the e2e test."""
    general_cfg = GeneralConfig(
        log_level="INFO",
        log_file=None,
        quiet=False,
        list_devices=False,
        clipboard=True,
    )
    asr_config = ASRConfig(
        server_ip="mock-asr-host",
        server_port=10300,
        input_device_index=0,
        input_device_name=None,
    )
    llm_config = LLMConfig(model="test-model", ollama_host="http://localhost:11434")
    tts_config = TTSConfig(
        enabled=False,
        server_ip="mock-tts-host",
        server_port=10200,
        voice_name=None,
        language=None,
        speaker=None,
        output_device_index=None,
        output_device_name=None,
        speed=1.0,
    )
    file_config = FileConfig(save_file=None)
    return general_cfg, asr_config, llm_config, tts_config, file_config


@pytest.mark.asyncio
@patch("agent_cli.agents.voice_assistant.process_instruction_and_respond", new_callable=AsyncMock)
@patch("agent_cli.agents.voice_assistant.get_instruction_from_audio", new_callable=AsyncMock)
@patch("agent_cli.agents.voice_assistant.asr.record_audio_with_manual_stop", new_callable=AsyncMock)
@patch("agent_cli.agents.voice_assistant.get_clipboard_text", return_value="test clipboard text")
@patch("agent_cli.agents.voice_assistant.setup_devices")
@patch("agent_cli.agents.voice_assistant.pyaudio_context")
async def test_voice_assistant_e2e(
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

    general_cfg, asr_config, llm_config, tts_config, file_config = get_configs()

    # This test focuses on the main loop, so we stop it after one run
    with patch("agent_cli.agents.voice_assistant.signal_handling_context") as mock_signal_context:
        mock_stop_event = MagicMock()
        mock_stop_event.is_set.return_value = False
        mock_signal_context.return_value.__enter__.return_value = mock_stop_event

        await _async_main(
            general_cfg=general_cfg,
            asr_config=asr_config,
            llm_config=llm_config,
            tts_config=tts_config,
            file_config=file_config,
        )

    # Assertions
    mock_get_clipboard.assert_called_once()
    mock_record_audio.assert_called_once()
    mock_get_instruction.assert_called_once_with(
        b"audio data",
        asr_config,
        ANY,
        False,  # noqa: FBT003
    )
    mock_process_instruction.assert_called_once_with(
        instruction="this is a test",
        original_text="test clipboard text",
        general_cfg=general_cfg,
        llm_config=llm_config,
        tts_config=tts_config,
        file_config=file_config,
        system_prompt=SYSTEM_PROMPT,
        agent_instructions=AGENT_INSTRUCTIONS,
        tts_output_device_index=None,
        live=ANY,
        logger=ANY,
    )
