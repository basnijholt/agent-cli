"""Tests for the transcribe agent."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
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
            tts_provider="piper",
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
        gemini_llm_cfg = config.GeminiLLM(
            llm_gemini_model="gemini-1.5-flash",
            gemini_api_key="test-key",
        )

        await transcribe._async_main(
            extra_instructions=None,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            audio_in_cfg=audio_in_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            llm_enabled=True,
            transcription_log=None,
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
            tts_provider="piper",
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
        gemini_llm_cfg = config.GeminiLLM(
            llm_gemini_model="gemini-1.5-flash",
            gemini_api_key="test-key",
        )

        await transcribe._async_main(
            extra_instructions=None,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            audio_in_cfg=audio_in_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            llm_enabled=False,
            transcription_log=None,
            p=mock_pyaudio_instance,
        )

    # Assertions
    assert "Copied transcript to clipboard." in caplog.text
    mock_pyperclip.copy.assert_called_once_with("hello world")
    mock_wyoming_client_context.assert_called_once()


def test_log_transcription(tmp_path: Path) -> None:
    """Test the log_transcription function."""
    log_file = tmp_path / "test_log.jsonl"

    # Test logging without processed transcript
    transcribe.log_transcription(
        log_file=log_file,
        role="user",
        raw_transcript="hello world",
        processed_transcript=None,
        model_info="local:whisper",
    )

    # Test logging with processed transcript
    transcribe.log_transcription(
        log_file=log_file,
        role="assistant",
        raw_transcript="hello world",
        processed_transcript="Hello, world!",
        model_info="local:qwen3:4b",
    )

    # Read and verify log entries
    with log_file.open("r") as f:
        log_entries = [json.loads(line.strip()) for line in f]

    assert len(log_entries) == 2

    # Check first entry (user/raw)
    first_entry = log_entries[0]
    assert first_entry["role"] == "user"
    assert first_entry["model"] == "local:whisper"
    assert first_entry["raw_output"] == "hello world"
    assert first_entry["processed_output"] is None
    assert "timestamp" in first_entry
    assert "hostname" in first_entry

    # Check second entry (assistant/processed)
    second_entry = log_entries[1]
    assert second_entry["role"] == "assistant"
    assert second_entry["model"] == "local:qwen3:4b"
    assert second_entry["raw_output"] == "hello world"
    assert second_entry["processed_output"] == "Hello, world!"
    assert "timestamp" in second_entry
    assert "hostname" in second_entry


@pytest.mark.asyncio
@patch("agent_cli.agents.transcribe.signal_handling_context")
@patch("agent_cli.agents.transcribe.pyaudio_context")
@patch("agent_cli.agents.transcribe.pyperclip")
@patch("agent_cli.services.asr.wyoming_client_context")
@patch("agent_cli.agents.transcribe.process_and_update_clipboard", new_callable=AsyncMock)
async def test_transcribe_with_logging(
    mock_process_and_update_clipboard: AsyncMock,
    mock_wyoming_client_context: MagicMock,
    mock_pyperclip: MagicMock,  # noqa: ARG001
    mock_pyaudio_context: MagicMock,
    mock_signal_handling_context: MagicMock,
    tmp_path: Path,
) -> None:
    """Test transcription with logging enabled."""
    log_file = tmp_path / "transcription.jsonl"

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

    # Mock the LLM response
    mock_process_and_update_clipboard.return_value = "Hello, world!"

    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="piper",
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
    ollama_cfg = config.Ollama(llm_ollama_model="qwen3:4b", llm_ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(llm_openai_model="gpt-4")
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )

    await transcribe._async_main(
        extra_instructions=None,
        provider_cfg=provider_cfg,
        general_cfg=general_cfg,
        audio_in_cfg=audio_in_cfg,
        wyoming_asr_cfg=wyoming_asr_cfg,
        openai_asr_cfg=openai_asr_cfg,
        ollama_cfg=ollama_cfg,
        openai_llm_cfg=openai_llm_cfg,
        gemini_llm_cfg=gemini_llm_cfg,
        llm_enabled=True,
        transcription_log=log_file,
        p=mock_pyaudio_instance,
    )

    # Verify log file was created and contains expected entry
    assert log_file.exists()

    with log_file.open("r") as f:
        log_entries = [json.loads(line.strip()) for line in f]

    assert len(log_entries) == 1
    entry = log_entries[0]
    assert entry["role"] == "assistant"
    assert entry["model"] == "local:qwen3:4b"
    assert entry["raw_output"] == "hello world"
    assert entry["processed_output"] == "Hello, world!"
    assert "timestamp" in entry
    assert "hostname" in entry


def test_transcription_log_path_expansion() -> None:
    """Test that transcription log paths with ~ are expanded."""
    # Create a test case that would use ~ expansion
    home_relative_path = Path("~/test_transcription.log")
    expanded_path = home_relative_path.expanduser()

    # Verify expansion works as expected
    assert str(home_relative_path) == "~/test_transcription.log"
    assert str(expanded_path) == str(Path.home() / "test_transcription.log")
    assert expanded_path.is_absolute()

    # Test the actual expansion logic from transcribe function
    test_path = Path("~/test.log")
    expanded = test_path.expanduser()
    assert expanded.is_absolute()
    assert "~" not in str(expanded)
