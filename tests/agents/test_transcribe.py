"""Tests for the transcribe agent."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.agents import transcribe
from tests.mocks.wyoming import MockASRClient


@pytest.mark.asyncio
@patch("agent_cli.agents.transcribe.process_and_update_clipboard", new_callable=AsyncMock)
@patch("agent_cli.services.asr.wyoming_client_context")
@patch("agent_cli.agents.transcribe.pyperclip")
@patch("agent_cli.agents.transcribe.pyaudio_context")
@patch("agent_cli.agents.transcribe.signal_handling_context")
async def test_transcribe_main_llm_enabled(
    mock_signal_handling_context: MagicMock,
    mock_pyaudio_context: MagicMock,
    mock_pyperclip: MagicMock,
    mock_wyoming_client_context: MagicMock,
    mock_process_and_update_clipboard: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the main function of the transcribe agent with LLM enabled."""
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
        wyoming_asr_cfg = config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=12345)
        openai_asr_cfg = config.OpenAIASR(asr_openai_model="whisper-1")
        ollama_cfg = config.Ollama(llm_ollama_model="test", llm_ollama_host="localhost")
        openai_llm_cfg = config.OpenAILLM(llm_openai_model="gpt-4")

        await transcribe._async_main(
            extra_instructions=None,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            audio_in_cfg=audio_in_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            llm_enabled=True,
            p=mock_pyaudio_instance,
        )

    # Assertions
    mock_process_and_update_clipboard.assert_called_once()
    mock_pyperclip.copy.assert_not_called()


@pytest.mark.asyncio
@patch("agent_cli.services.asr.wyoming_client_context")
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
        wyoming_asr_cfg = config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=12345)
        openai_asr_cfg = config.OpenAIASR(asr_openai_model="whisper-1")
        ollama_cfg = config.Ollama(llm_ollama_model="", llm_ollama_host="")
        openai_llm_cfg = config.OpenAILLM(llm_openai_model="")

        await transcribe._async_main(
            extra_instructions=None,
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
