"""End-to-end tests for the voice assistant agent with simplified mocks."""

from __future__ import annotations

import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from agent_cli.agents._config import (
    ASRConfig,
    FileConfig,
    GeneralConfig,
    LLMConfig,
    TTSConfig,
)
from agent_cli.agents._voice_agent_common import async_main_voice_agent
from agent_cli.agents.voice_assistant import AGENT_INSTRUCTIONS, SYSTEM_PROMPT
from agent_cli.utils import InteractiveStopEvent
from tests.mocks.audio import MockPyAudio


def get_configs() -> tuple[GeneralConfig, ASRConfig, LLMConfig, TTSConfig, FileConfig]:
    """Get all the necessary configs for the e2e test."""
    general_cfg = GeneralConfig(log_level="INFO", log_file=None, quiet=False, clipboard=True)
    asr_config = ASRConfig(
        server_ip="mock-asr-host",
        server_port=10300,
        input_device_index=0,
        input_device_name=None,
        list_input_devices=False,
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
        list_output_devices=False,
        speed=1.0,
    )
    file_config = FileConfig(save_file=None)
    return general_cfg, asr_config, llm_config, tts_config, file_config


@pytest.mark.asyncio
@patch("agent_cli.agents._voice_agent_common.process_and_update_clipboard", new_callable=AsyncMock)
@patch(
    "agent_cli.asr.transcribe_recorded_audio",
    new_callable=AsyncMock,
    return_value="this is a test",
)
@patch("agent_cli.agents._voice_agent_common.pyaudio_context")
@patch("agent_cli.agents._voice_agent_common.signal_handling_context")
@patch(
    "agent_cli.agents._voice_agent_common.get_clipboard_text",
    return_value="test clipboard text",
)
async def test_voice_assistant_e2e(
    mock_get_clipboard: MagicMock,
    mock_signal_context: MagicMock,
    mock_pyaudio_context: MagicMock,
    mock_process_audio: AsyncMock,
    mock_process_clipboard: AsyncMock,
) -> None:
    """Test end-to-end voice assistant functionality with simplified mocks."""
    mock_record_audio = AsyncMock(return_value=b"audio data")
    stop_event = InteractiveStopEvent()
    # Stop the agent after one loop
    asyncio.get_event_loop().call_later(0.1, stop_event.set)
    mock_signal_context.return_value.__enter__.return_value = stop_event

    mock_pyaudio_instance = MockPyAudio(
        [{"maxInputChannels": 1, "maxOutputChannels": 0, "index": 0, "defaultSampleRate": 44100.0}],
    )
    mock_pyaudio_context.return_value.__enter__.return_value = mock_pyaudio_instance

    general_cfg, asr_config, llm_config, tts_config, file_config = get_configs()

    await async_main_voice_agent(
        recording_func=mock_record_audio,
        get_original_text_func=mock_get_clipboard,
        general_cfg=general_cfg,
        asr_config=asr_config,
        llm_config=llm_config,
        tts_config=tts_config,
        file_config=file_config,
        system_prompt=SYSTEM_PROMPT,
        agent_instructions=AGENT_INSTRUCTIONS,
    )

    # Assertions
    mock_record_audio.assert_called_once()
    mock_process_audio.assert_called_once_with(
        b"audio data",
        asr_server_ip="mock-asr-host",
        asr_server_port=10300,
        logger=ANY,
        quiet=False,
    )
    mock_process_clipboard.assert_called_once()
