"""End-to-end tests for the transcribe agent with minimal mocking."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.agents.transcribe import _async_main
from tests.mocks.audio import MockPyAudio

if TYPE_CHECKING:
    from rich.console import Console


@pytest.mark.asyncio
@patch("agent_cli.agents.transcribe.signal_handling_context")
@patch("agent_cli.agents.transcribe.get_asr_service")
@patch("agent_cli.core.audio.pyaudio.PyAudio")
async def test_transcribe_e2e(
    mock_pyaudio_class: MagicMock,
    mock_get_asr_service: MagicMock,
    mock_signal_handling_context: MagicMock,
    mock_pyaudio_device_info: list[dict],
    mock_console: Console,
) -> None:
    """Test end-to-end transcription with simplified mocks."""
    # Setup mock PyAudio
    mock_pyaudio_instance = MockPyAudio(mock_pyaudio_device_info)
    mock_pyaudio_class.return_value = mock_pyaudio_instance

    transcript_text = "This is a test transcription."
    mock_get_asr_service.return_value.transcribe.return_value = transcript_text

    # Setup stop event
    stop_event = asyncio.Event()
    mock_signal_handling_context.return_value.__enter__.return_value = stop_event
    asyncio.get_event_loop().call_later(0.1, stop_event.set)

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
        clipboard=False,
    )
    wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="mock-host", wyoming_asr_port=10300)
    openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")
    ollama_cfg = config.Ollama(ollama_model="", ollama_host="")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="")

    with patch("agent_cli.core.utils.console", mock_console):
        await _async_main(
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            llm_enabled=False,
        )

    # Assert that the final transcript is in the console output
    output = mock_console.file.getvalue()
    assert "test" in output

    # Ensure the mock client was used
    mock_get_asr_service.assert_called_once()
