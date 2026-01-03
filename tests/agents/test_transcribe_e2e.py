"""End-to-end tests for the transcribe agent with minimal mocking."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.agents.transcribe import _async_main
from tests.mocks.audio import MockSoundDeviceStream
from tests.mocks.wyoming import MockASRClient

if TYPE_CHECKING:
    from rich.console import Console


@pytest.mark.asyncio
@patch("agent_cli.agents.transcribe.signal_handling_context")
@patch("agent_cli.services.asr.wyoming_client_context")
@patch("agent_cli.services.asr.open_audio_stream")
@patch("agent_cli.services.asr.setup_input_stream")
async def test_transcribe_e2e(
    mock_setup_input_stream: MagicMock,
    mock_open_audio_stream: MagicMock,
    mock_wyoming_client_context: MagicMock,
    mock_signal_handling_context: MagicMock,
    mock_console: Console,
) -> None:
    """Test end-to-end transcription with simplified mocks."""
    # Setup mock stream
    mock_stream = MockSoundDeviceStream(input=True)
    mock_open_audio_stream.return_value.__enter__.return_value = mock_stream
    mock_setup_input_stream.return_value = {"dtype": "int16"}

    # Setup mock Wyoming client
    transcript_text = "This is a test transcription."
    mock_asr_client = MockASRClient(transcript_text)
    mock_wyoming_client_context.return_value.__aenter__.return_value = mock_asr_client

    # Setup stop event
    stop_event = asyncio.Event()
    mock_signal_handling_context.return_value.__enter__.return_value = stop_event
    asyncio.get_event_loop().call_later(0.1, stop_event.set)

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
        clipboard=False,
    )
    audio_in_cfg = config.AudioInput(input_device_index=0)
    wyoming_asr_cfg = config.WyomingASR(asr_wyoming_ip="mock-host", asr_wyoming_port=10300)
    openai_asr_cfg = config.OpenAIASR(asr_openai_model="whisper-1")
    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key="test-key",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="", llm_ollama_host="")
    openai_llm_cfg = config.OpenAILLM(llm_openai_model="", openai_base_url=None)
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )

    with patch("agent_cli.core.utils.console", mock_console):
        await _async_main(
            extra_instructions=None,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            audio_in_cfg=audio_in_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            gemini_asr_cfg=gemini_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            llm_enabled=False,
            transcription_log=None,
            save_recording=False,
        )

    # Assert that the final transcript is in the console output
    output = mock_console.file.getvalue()
    assert transcript_text in output

    # Ensure the mock client was used
    mock_wyoming_client_context.assert_called_once()
