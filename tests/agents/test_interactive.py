"""Tests for the chat agent."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_cli.agents import config
from agent_cli.agents.chat import (
    ConversationEntry,
    _async_main,
    _format_conversation_for_llm,
    _load_conversation_history,
    _save_conversation_history,
)
from agent_cli.utils import InteractiveStopEvent

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def history_file(tmp_path: Path) -> Path:
    """Create a temporary history file."""
    return tmp_path / "conversation.json"


def test_load_and_save_conversation_history(history_file: Path) -> None:
    """Test saving and loading conversation history."""
    # 1. Test loading from a non-existent file
    history = _load_conversation_history(history_file, 10)
    assert history == []

    # 2. Test saving and then loading
    now = datetime.now(UTC).isoformat()
    history_to_save: list[ConversationEntry] = [
        {"role": "user", "content": "Hello", "timestamp": now},
        {"role": "assistant", "content": "Hi there!", "timestamp": now},
    ]
    _save_conversation_history(history_file, history_to_save)

    loaded_history = _load_conversation_history(history_file, 10)
    assert loaded_history == history_to_save

    # 3. Test loading with last_n_messages=0
    loaded_history_zero = _load_conversation_history(history_file, 0)
    assert loaded_history_zero == []


def test_format_conversation_for_llm() -> None:
    """Test formatting conversation history for the LLM."""
    # 1. Test with no history
    assert _format_conversation_for_llm([]) == "No previous conversation."

    # 2. Test with history
    now = datetime.now(UTC)
    history: list[ConversationEntry] = [
        {
            "role": "user",
            "content": "What's the weather?",
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
        },
        {
            "role": "assistant",
            "content": "It's sunny.",
            "timestamp": (now - timedelta(minutes=4)).isoformat(),
        },
    ]
    formatted = _format_conversation_for_llm(history)
    assert "user (5 minutes ago): What's the weather?" in formatted
    assert "assistant (4 minutes ago): It's sunny." in formatted


@pytest.mark.asyncio
async def test_async_main_list_devices(tmp_path: Path) -> None:
    """Test the async_main function with list_input_devices=True."""
    general_cfg = config.General(
        log_level="INFO",
        log_file=None,
        quiet=False,
        list_devices=True,
        clipboard=False,
    )
    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    history_cfg = config.History(history_dir=tmp_path)
    audio_in_cfg = config.AudioInput()
    wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="localhost", wyoming_asr_port=1234)
    openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")
    ollama_cfg = config.Ollama(ollama_model="test-model", ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4")
    audio_out_cfg = config.AudioOutput()
    wyoming_tts_cfg = config.WyomingTTS(wyoming_tts_ip="localhost", wyoming_tts_port=5678)
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")

    with (
        patch("agent_cli.agents.chat.pyaudio_context"),
        patch(
            "agent_cli.agents.chat.setup_devices",
        ) as mock_setup_devices,
    ):
        mock_setup_devices.return_value = None
        await _async_main(
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            history_cfg=history_cfg,
            audio_in_cfg=audio_in_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            audio_out_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
        )
        mock_setup_devices.assert_called_once()


@pytest.mark.asyncio
async def test_async_main_list_output_devices(tmp_path: Path) -> None:
    """Test the async_main function with list_devices=True."""
    general_cfg = config.General(
        log_level="INFO",
        log_file=None,
        quiet=False,
        list_devices=False,
        clipboard=False,
    )
    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    history_cfg = config.History(history_dir=tmp_path)
    audio_in_cfg = config.AudioInput()
    wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="localhost", wyoming_asr_port=1234)
    openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")
    ollama_cfg = config.Ollama(ollama_model="test-model", ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4")
    audio_out_cfg = config.AudioOutput()
    wyoming_tts_cfg = config.WyomingTTS(wyoming_tts_ip="localhost", wyoming_tts_port=5678)
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")

    with (
        patch("agent_cli.agents.chat.pyaudio_context"),
        patch(
            "agent_cli.agents.chat.setup_devices",
        ) as mock_setup_devices,
    ):
        mock_setup_devices.return_value = None
        await _async_main(
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            history_cfg=history_cfg,
            audio_in_cfg=audio_in_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            audio_out_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
        )
        mock_setup_devices.assert_called_once()


@pytest.mark.asyncio
async def test_async_main_full_loop(tmp_path: Path) -> None:
    """Test a full loop of the chat agent's async_main function."""
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    general_cfg = config.General(
        log_level="INFO",
        log_file=None,
        list_devices=False,
        quiet=False,
        clipboard=False,
    )
    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    history_cfg = config.History(history_dir=history_dir)
    audio_in_cfg = config.AudioInput(input_device_index=1)
    wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="localhost", wyoming_asr_port=1234)
    openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")
    ollama_cfg = config.Ollama(ollama_model="test-model", ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4")
    audio_out_cfg = config.AudioOutput(enable_tts=True, output_device_index=1)
    wyoming_tts_cfg = config.WyomingTTS(
        wyoming_tts_ip="localhost",
        wyoming_tts_port=5678,
        wyoming_voice="test-voice",
    )
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")

    with (
        patch("agent_cli.agents.chat.pyaudio_context"),
        patch("agent_cli.agents.chat.setup_devices", return_value=(1, "mock_input", 1)),
        patch("agent_cli.agents.chat.asr.get_transcriber") as mock_get_transcriber,
        patch(
            "agent_cli.agents.chat.get_llm_response",
            new_callable=AsyncMock,
        ) as mock_llm_response,
        patch(
            "agent_cli.agents.chat.handle_tts_playback",
            new_callable=AsyncMock,
        ) as mock_tts,
        patch("agent_cli.agents.chat.signal_handling_context") as mock_signal,
    ):
        # Simulate a single loop by controlling the mock stop_event's is_set method
        mock_stop_event = MagicMock(spec=InteractiveStopEvent)
        mock_stop_event.is_set.side_effect = [False, True]  # Run loop once, then stop
        mock_stop_event.clear = MagicMock()  # Mock the clear method

        mock_transcriber = AsyncMock(return_value="Mocked instruction")
        mock_get_transcriber.return_value = mock_transcriber
        mock_llm_response.return_value = "Mocked response"
        mock_signal.return_value.__enter__.return_value = mock_stop_event

        await _async_main(
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            history_cfg=history_cfg,
            audio_in_cfg=audio_in_cfg,
            wyoming_asr_cfg=wyoming_asr_cfg,
            openai_asr_cfg=openai_asr_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            audio_out_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
        )

        # Verify that the core functions were called
        mock_get_transcriber.assert_called_once()
        mock_transcriber.assert_called_once()
        mock_llm_response.assert_called_once()
        assert mock_stop_event.clear.call_count == 2  # Called after ASR and at end of turn
        mock_tts.assert_called_with(
            text="Mocked response",
            provider_config=provider_cfg,
            audio_output_config=audio_out_cfg,
            wyoming_tts_config=wyoming_tts_cfg,
            openai_tts_config=openai_tts_cfg,
            openai_llm_config=openai_llm_cfg,
            save_file=None,
            quiet=False,
            logger=mock_tts.call_args.kwargs["logger"],
            play_audio=True,
            stop_event=mock_tts.call_args.kwargs["stop_event"],
            live=mock_tts.call_args.kwargs["live"],
        )

        # Verify that history was saved
        history_file = history_dir / "conversation.json"
        assert history_file.exists()
        with history_file.open("r") as f:
            history = json.load(f)

        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Mocked instruction"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Mocked response"
