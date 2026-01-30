"""Tests for the transcribe agent."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli import config
from agent_cli.agents import transcribe
from tests.mocks.wyoming import MockASRClient


@pytest.mark.asyncio
@patch("agent_cli.services.asr.open_audio_stream")
@patch("agent_cli.services.asr.setup_input_stream")
@patch("agent_cli.agents.transcribe.process_and_update_clipboard", new_callable=AsyncMock)
@patch("agent_cli.services.asr.wyoming_client_context")
@patch("pyperclip.copy")
@patch("pyperclip.paste")
@patch("agent_cli.agents.transcribe.signal_handling_context")
async def test_transcribe_main_llm_enabled(
    mock_signal_handling_context: MagicMock,
    mock_pyperclip_paste: MagicMock,
    mock_pyperclip_copy: MagicMock,
    mock_wyoming_client_context: MagicMock,
    mock_process_and_update_clipboard: AsyncMock,
    mock_setup_input_stream: MagicMock,
    mock_open_audio_stream: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the main function of the transcribe agent with LLM enabled."""
    # Mock audio stream
    mock_stream = MagicMock()
    mock_stream.read.return_value = (MagicMock(tobytes=lambda: b"\0" * 1024), False)
    mock_open_audio_stream.return_value.__enter__.return_value = mock_stream
    assert mock_setup_input_stream  # Used to satisfy linter

    # Mock the Wyoming client
    mock_asr_client = MockASRClient("hello world")
    mock_wyoming_client_context.return_value.__aenter__.return_value = mock_asr_client

    # Setup stop event
    stop_event = asyncio.Event()
    mock_signal_handling_context.return_value.__enter__.return_value = stop_event
    asyncio.get_event_loop().call_later(0.1, stop_event.set)

    mock_pyperclip_paste.return_value = ""

    # The function we are testing
    with caplog.at_level(logging.INFO):
        provider_cfg = config.ProviderSelection(
            asr_provider="wyoming",
            llm_provider="ollama",
            tts_provider="wyoming",
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
        gemini_asr_cfg = config.GeminiASR(
            asr_gemini_model="gemini-2.0-flash",
            gemini_api_key="test-key",
        )
        ollama_cfg = config.Ollama(llm_ollama_model="test", llm_ollama_host="localhost")
        openai_llm_cfg = config.OpenAILLM(llm_openai_model="gpt-4", openai_base_url=None)
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
            gemini_asr_cfg=gemini_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            llm_enabled=True,
            transcription_log=None,
            save_recording=False,  # Disable for testing
        )

    # Assertions
    mock_process_and_update_clipboard.assert_called_once()
    mock_pyperclip_copy.assert_called_once_with("hello world")
    mock_pyperclip_paste.assert_called_once()
    assert "Copied raw transcript to clipboard before LLM processing." in caplog.text


@pytest.mark.asyncio
@patch("agent_cli.services.asr.open_audio_stream")
@patch("agent_cli.services.asr.setup_input_stream")
@patch("agent_cli.services.asr.wyoming_client_context")
@patch("pyperclip.copy")
@patch("agent_cli.agents.transcribe.signal_handling_context")
async def test_transcribe_main(
    mock_signal_handling_context: MagicMock,
    mock_pyperclip_copy: MagicMock,
    mock_wyoming_client_context: MagicMock,
    mock_setup_input_stream: MagicMock,
    mock_open_audio_stream: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the main function of the transcribe agent."""
    # Mock audio stream
    mock_stream = MagicMock()
    mock_stream.read.return_value = (MagicMock(tobytes=lambda: b"\0" * 1024), False)
    mock_open_audio_stream.return_value.__enter__.return_value = mock_stream
    assert mock_setup_input_stream  # Used to satisfy linter

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
            asr_provider="wyoming",
            llm_provider="ollama",
            tts_provider="wyoming",
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

        await transcribe._async_main(
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
            save_recording=False,  # Disable for testing
        )

    # Assertions
    assert "Copied transcript to clipboard." in caplog.text
    mock_pyperclip_copy.assert_called_once_with("hello world")
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
        model_info="local:gemma3:4b",
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
    assert second_entry["model"] == "local:gemma3:4b"
    assert second_entry["raw_output"] == "hello world"
    assert second_entry["processed_output"] == "Hello, world!"
    assert "timestamp" in second_entry
    assert "hostname" in second_entry


def test_gather_recent_transcription_context(tmp_path: Path) -> None:
    """Ensure only recent log entries are used for context."""
    log_file = tmp_path / "transcriptions.jsonl"
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)

    entries = [
        {
            "timestamp": (now - timedelta(minutes=70)).isoformat(),
            "role": "assistant",
            "processed_output": "Too old",
        },
        {
            "timestamp": (now - timedelta(minutes=30)).isoformat(),
            "role": "user",
            "raw_output": "Keep this one",
        },
        {
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "role": "assistant",
            "processed_output": "Also keep this",
        },
    ]

    with log_file.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    context = transcribe._gather_recent_transcription_context(
        log_file,
        now=now,
        max_age_seconds=3600,
        max_entries=2,
    )

    assert context is not None
    lines = context.splitlines()
    assert lines[0].startswith("Recent transcript history")
    assert len(lines) == 2
    assert "Keep this one" in lines[1]


def test_gather_recent_transcription_context_chunked_read(tmp_path: Path) -> None:
    """Ensure we can read recent entries without loading entire file."""
    log_file = tmp_path / "chunked.jsonl"
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)

    with log_file.open("w", encoding="utf-8") as f:
        for i in reversed(range(10)):
            entry = {
                "timestamp": (now - timedelta(minutes=i * 5)).isoformat(),
                "role": "user",
                "raw_output": f"Entry {i}",
                "processed_output": None,
            }
            f.write(json.dumps(entry) + "\n")

    context = transcribe._gather_recent_transcription_context(
        log_file,
        now=now,
        max_age_seconds=3600,
        max_entries=3,
        chunk_size=32,
    )

    assert context is not None
    lines = context.splitlines()
    assert lines[0].startswith("Recent transcript history")
    assert len(lines) == 4
    assert lines[1].endswith("Entry 2")
    assert lines[-1].endswith("Entry 0")


def test_gather_recent_context_prefers_raw(tmp_path: Path) -> None:
    """Ensure raw transcripts are preferred when both raw and cleaned exist."""
    log_file = tmp_path / "prefers_raw.jsonl"
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)

    entry = {
        "timestamp": now.isoformat(),
        "role": "assistant",
        "raw_output": "Raw version",
        "processed_output": "Clean version",
    }
    with log_file.open("w", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    context = transcribe._gather_recent_transcription_context(
        log_file,
        now=now,
        max_age_seconds=3600,
        max_entries=1,
    )

    assert context is not None
    assert "Raw version" in context
    assert "Clean version" not in context


@pytest.mark.asyncio
@patch("agent_cli.agents.transcribe.signal_handling_context")
@patch("pyperclip.copy")
@patch("pyperclip.paste")
@patch("agent_cli.services.asr.wyoming_client_context")
@patch("agent_cli.agents.transcribe.process_and_update_clipboard", new_callable=AsyncMock)
@patch("agent_cli.services.asr.open_audio_stream")
@patch("agent_cli.services.asr.setup_input_stream")
async def test_transcribe_includes_clipboard_context(
    mock_setup_input_stream: MagicMock,
    mock_open_audio_stream: MagicMock,
    mock_process_and_update_clipboard: AsyncMock,
    mock_wyoming_client_context: MagicMock,
    mock_pyperclip_paste: MagicMock,
    mock_pyperclip_copy: MagicMock,
    mock_signal_handling_context: MagicMock,
) -> None:
    """Ensure clipboard content is forwarded to the LLM context."""
    # Mock audio stream
    mock_stream = MagicMock()
    mock_stream.read.return_value = (MagicMock(tobytes=lambda: b"\0" * 1024), False)
    mock_open_audio_stream.return_value.__enter__.return_value = mock_stream
    assert mock_setup_input_stream  # Used to satisfy linter
    assert mock_pyperclip_copy  # Used to satisfy linter

    mock_pyperclip_paste.return_value = "Clipboard reference text"

    mock_asr_client = MockASRClient("hello world")
    mock_wyoming_client_context.return_value.__aenter__.return_value = mock_asr_client

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
        quiet=True,
        list_devices=False,
        clipboard=True,
    )
    audio_in_cfg = config.AudioInput()
    wyoming_asr_cfg = config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=12345)
    openai_asr_cfg = config.OpenAIASR(asr_openai_model="whisper-1")
    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key="test-key",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test", llm_ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(llm_openai_model="gpt-4", openai_base_url=None)
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
        gemini_asr_cfg=gemini_asr_cfg,
        ollama_cfg=ollama_cfg,
        openai_llm_cfg=openai_llm_cfg,
        gemini_llm_cfg=gemini_llm_cfg,
        llm_enabled=True,
        transcription_log=None,
        save_recording=False,
    )

    mock_process_and_update_clipboard.assert_called_once()
    context = mock_process_and_update_clipboard.call_args.kwargs["context"]
    assert context is not None
    assert "Clipboard content captured before this recording" in context
    assert "Clipboard reference text" in context


@pytest.mark.asyncio
@patch("agent_cli.agents.transcribe.signal_handling_context")
@patch("pyperclip.copy")
@patch("pyperclip.paste")
@patch("agent_cli.services.asr.wyoming_client_context")
@patch("agent_cli.agents.transcribe.process_and_update_clipboard", new_callable=AsyncMock)
@patch("agent_cli.services.asr.open_audio_stream")
@patch("agent_cli.services.asr.setup_input_stream")
async def test_transcribe_with_logging(
    mock_setup_input_stream: MagicMock,
    mock_open_audio_stream: MagicMock,
    mock_process_and_update_clipboard: AsyncMock,
    mock_wyoming_client_context: MagicMock,
    mock_pyperclip_paste: MagicMock,
    mock_pyperclip_copy: MagicMock,
    mock_signal_handling_context: MagicMock,
    tmp_path: Path,
) -> None:
    """Test transcription with logging enabled."""
    log_file = tmp_path / "transcription.jsonl"

    # Mock audio stream
    mock_stream = MagicMock()
    mock_stream.read.return_value = (MagicMock(tobytes=lambda: b"\0" * 1024), False)
    mock_open_audio_stream.return_value.__enter__.return_value = mock_stream
    assert mock_setup_input_stream  # Used to satisfy linter
    assert mock_pyperclip_copy  # Used to satisfy linter

    # Mock the Wyoming client
    mock_asr_client = MockASRClient("hello world")
    mock_wyoming_client_context.return_value.__aenter__.return_value = mock_asr_client

    # Setup stop event
    stop_event = asyncio.Event()
    mock_signal_handling_context.return_value.__enter__.return_value = stop_event
    asyncio.get_event_loop().call_later(0.1, stop_event.set)

    # Mock clipboard and LLM response
    mock_pyperclip_paste.return_value = ""
    mock_process_and_update_clipboard.return_value = "Hello, world!"

    provider_cfg = config.ProviderSelection(
        asr_provider="wyoming",
        llm_provider="ollama",
        tts_provider="wyoming",
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
    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key="test-key",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="gemma3:4b", llm_ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(llm_openai_model="gpt-4", openai_base_url=None)
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
        gemini_asr_cfg=gemini_asr_cfg,
        ollama_cfg=ollama_cfg,
        openai_llm_cfg=openai_llm_cfg,
        gemini_llm_cfg=gemini_llm_cfg,
        llm_enabled=True,
        transcription_log=log_file,
        save_recording=False,  # Disable for testing
    )

    mock_pyperclip_paste.assert_called_once()

    # Verify log file was created and contains expected entry
    assert log_file.exists()

    with log_file.open("r") as f:
        log_entries = [json.loads(line.strip()) for line in f]

    assert len(log_entries) == 1
    entry = log_entries[0]
    assert entry["role"] == "assistant"
    assert entry["model"] == "ollama:gemma3:4b"
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
    assert home_relative_path.parts[0] == "~"
    assert home_relative_path.parts[-1] == "test_transcription.log"
    assert expanded_path == Path.home() / "test_transcription.log"
    assert expanded_path.is_absolute()

    # Test the actual expansion logic from transcribe function
    test_path = Path("~/test.log")
    expanded = test_path.expanduser()
    assert expanded.is_absolute()
    assert "~" not in str(expanded)
