"""Tests for the chat agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from agent_cli.agents import config
from agent_cli.agents.chat import (
    _async_main,
    _handle_conversation_turn,
)
from agent_cli.cli import app
from agent_cli.utils import InteractiveStopEvent


@pytest.mark.asyncio
async def test_handle_conversation_turn_no_instruction():
    """Test that the conversation turn exits early if no instruction is given."""
    mock_p = MagicMock()
    stop_event = InteractiveStopEvent()
    conversation_history = []
    general_cfg = config.General(log_level="INFO", log_file=None, quiet=True, list_devices=True)
    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    history_cfg = config.History()
    audio_in_cfg = config.AudioInput()
    wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="localhost", wyoming_asr_port=10300)
    openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")
    ollama_cfg = config.Ollama(ollama_model="test-model", ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4o-mini")
    audio_out_cfg = config.AudioOutput()
    wyoming_tts_cfg = config.WyomingTTS(wyoming_tts_ip="localhost", wyoming_tts_port=10200)
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")
    mock_live = MagicMock()

    with patch("agent_cli.agents.chat.asr.get_transcriber") as mock_get_transcriber:
        mock_transcriber = AsyncMock(return_value="")
        mock_get_transcriber.return_value = mock_transcriber
        await _handle_conversation_turn(
            p=mock_p,
            stop_event=stop_event,
            conversation_history=conversation_history,
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
            live=mock_live,
        )
        mock_get_transcriber.assert_called_once()
        mock_transcriber.assert_awaited_once()
    assert not conversation_history


def test_chat_command_stop_and_status():
    """Test the stop and status flags of the chat command."""
    runner = CliRunner()
    with patch(
        "agent_cli.agents.chat.stop_or_status_or_toggle",
        return_value=True,
    ) as mock_stop_or_status:
        result = runner.invoke(app, ["chat", "--stop"])
        assert result.exit_code == 0
        mock_stop_or_status.assert_called_with(
            "chat",
            "chat agent",
            True,  # noqa: FBT003, stop
            False,  # noqa: FBT003, status
            False,  # noqa: FBT003, toggle
            quiet=False,
        )

        result = runner.invoke(app, ["chat", "--status"])
        assert result.exit_code == 0
        mock_stop_or_status.assert_called_with(
            "chat",
            "chat agent",
            False,  # noqa: FBT003, stop
            True,  # noqa: FBT003, status
            False,  # noqa: FBT003, toggle
            quiet=False,
        )


def test_chat_command_list_output_devices():
    """Test the list-output-devices flag."""
    runner = CliRunner()
    with (
        patch("agent_cli.agents.chat.setup_devices") as mock_setup_devices,
        patch("agent_cli.agents.chat.pyaudio_context") as mock_pyaudio_context,
    ):
        mock_setup_devices.return_value = None
        result = runner.invoke(app, ["chat", "--list-devices"])
        assert result.exit_code == 0
        mock_pyaudio_context.assert_called_once()
        mock_setup_devices.assert_called_once()


@pytest.mark.asyncio
async def test_async_main_exception_handling():
    """Test that exceptions in async_main are caught and logged."""
    general_cfg = config.General(log_level="INFO", log_file=None, quiet=False, list_devices=True)
    provider_cfg = config.ProviderSelection(
        asr_provider="local",
        llm_provider="local",
        tts_provider="local",
    )
    history_cfg = config.History()
    audio_in_cfg = config.AudioInput()
    wyoming_asr_cfg = config.WyomingASR(wyoming_asr_ip="localhost", wyoming_asr_port=10300)
    openai_asr_cfg = config.OpenAIASR(openai_asr_model="whisper-1")
    ollama_cfg = config.Ollama(ollama_model="test-model", ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(openai_llm_model="gpt-4o-mini")
    audio_out_cfg = config.AudioOutput()
    wyoming_tts_cfg = config.WyomingTTS(wyoming_tts_ip="localhost", wyoming_tts_port=10200)
    openai_tts_cfg = config.OpenAITTS(openai_tts_model="tts-1", openai_tts_voice="alloy")

    with (
        patch("agent_cli.agents.chat.pyaudio_context", side_effect=Exception("Test error")),
        patch("agent_cli.agents.chat.console") as mock_console,
    ):
        with pytest.raises(Exception, match="Test error"):
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
        mock_console.print_exception.assert_called_once()
