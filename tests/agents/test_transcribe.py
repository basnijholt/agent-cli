"""Tests for the transcribe agent."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock, patch

import pytest

from agent_cli.agents import config, transcribe
from tests.mocks.wyoming import MockASRClient


@pytest.mark.asyncio()
@patch("agent_cli.asr.wyoming_client_context")
@patch("agent_cli.agents.transcribe.pyperclip")
@patch("agent_cli.agents.transcribe.pyaudio_context")
@patch("agent_cli.agents.transcribe.signal_handling_context")
async def test_transcribe_main(
    mock_signal_handling_context: MagicMock,
    mock_pyaudio_context: MagicMock,
    mock_pyperclip: MagicMock,
    mock_wyoming_client_context: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the main function of the transcribe agent."""
    # Mock the pyaudio context manager
    mock_pyaudio_instance = MagicMock()
    mock_pyaudio_context.return_value.__enter__.return_value = mock_pyaudio_instance

    # Mock the Wyoming client
    mock_asr_client = MockASRClient("hello world")
    mock_wyoming_client_context.return_value.__aenter__.return_value = mock_asr_client

    # Setup stop event
    stop_event = asyncio.Event()
    mock_signal_handling_context.return_value.__enter__.return_value = stop_event
    asyncio.get_event_loop().call_later(0.1, stop_event.set)

    # The function we are testing
    with caplog.at_level(logging.INFO):
        provider_cfg = config.ProviderSelection(
            asr_provider="local",
            llm_provider="local",
            tts_provider="local",
        )
        general_cfg = config.General(
            log_level="INFO",
            log_file=None,
            quiet=True,
            list_devices=False,
            clipboard=True,
        )
        audio_in_cfg = config.AudioInput()
        wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="localhost", wyoming_asr_port=12345)
        openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")
        ollama_cfg = config.Ollama(ollama_model="", ollama_host="")
        openai_llm_cfg = config.OpenAILLM(openai_llm_model="")

        await transcribe._async_main(
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            audio_in_cfg=audio_in_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            llm_enabled=False,
            p=mock_pyaudio_instance,
        )

    # Assertions
    assert "Copied transcript to clipboard." in caplog.text
    mock_pyperclip.copy.assert_called_once_with("hello world")
    mock_wyoming_client_context.assert_called_once()
