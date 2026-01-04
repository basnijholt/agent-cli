"""Tests for the chat agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from agent_cli import config
from agent_cli.agents.chat import (
    _async_main,
    _handle_conversation_turn,
)
from agent_cli.cli import app
from agent_cli.constants import DEFAULT_OPENAI_MODEL
from agent_cli.core.chat_state import ChatSessionState
from agent_cli.core.utils import InteractiveStopEvent


@pytest.mark.asyncio
async def test_handle_conversation_turn_no_llm_response():
    """Test that the conversation turn handles no response from the LLM."""
    stop_event = InteractiveStopEvent()
    chat_state = ChatSessionState(tts_enabled=False)
    general_cfg = config.General(log_level="INFO", log_file=None, quiet=True, list_devices=True)
    provider_cfg = config.ProviderSelection(
        asr_provider="wyoming",
        llm_provider="ollama",
        tts_provider="wyoming",
    )
    history_cfg = config.History()
    ollama_cfg = config.Ollama(llm_ollama_model="test-model", llm_ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(llm_openai_model=DEFAULT_OPENAI_MODEL, openai_base_url=None)
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )
    audio_out_cfg = config.AudioOutput()
    wyoming_tts_cfg = config.WyomingTTS(tts_wyoming_ip="localhost", tts_wyoming_port=10200)
    openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
    kokoro_tts_cfg = config.KokoroTTS(
        tts_kokoro_model="tts-1",
        tts_kokoro_voice="alloy",
        tts_kokoro_host="http://localhost:8000/v1",
    )
    gemini_tts_cfg = config.GeminiTTS(
        tts_gemini_model="gemini-2.5-flash-preview-tts",
        tts_gemini_voice="Kore",
        gemini_api_key="test-key",
    )
    mock_live = MagicMock()

    with (
        patch(
            "agent_cli.agents.chat.get_llm_response",
            new_callable=AsyncMock,
        ) as mock_llm_response,
    ):
        mock_llm_response.return_value = ""
        await _handle_conversation_turn(
            instruction="test instruction",
            chat_state=chat_state,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            history_cfg=history_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            audio_out_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
            kokoro_tts_cfg=kokoro_tts_cfg,
            gemini_tts_cfg=gemini_tts_cfg,
            live=mock_live,
            stop_event=stop_event,
        )
        mock_llm_response.assert_awaited_once()

    # User message added but no assistant response (empty LLM response)
    assert len(chat_state.conversation_history) == 1
    assert chat_state.conversation_history[0]["role"] == "user"


@pytest.mark.asyncio
async def test_handle_conversation_turn_with_response():
    """Test that the conversation turn adds both user and assistant messages."""
    stop_event = InteractiveStopEvent()
    chat_state = ChatSessionState(tts_enabled=False)
    general_cfg = config.General(log_level="INFO", log_file=None, quiet=True, list_devices=True)
    provider_cfg = config.ProviderSelection(
        asr_provider="wyoming",
        llm_provider="ollama",
        tts_provider="wyoming",
    )
    history_cfg = config.History()
    ollama_cfg = config.Ollama(llm_ollama_model="test-model", llm_ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(llm_openai_model=DEFAULT_OPENAI_MODEL, openai_base_url=None)
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )
    audio_out_cfg = config.AudioOutput()
    wyoming_tts_cfg = config.WyomingTTS(tts_wyoming_ip="localhost", tts_wyoming_port=10200)
    openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
    kokoro_tts_cfg = config.KokoroTTS(
        tts_kokoro_model="tts-1",
        tts_kokoro_voice="alloy",
        tts_kokoro_host="http://localhost:8000/v1",
    )
    gemini_tts_cfg = config.GeminiTTS(
        tts_gemini_model="gemini-2.5-flash-preview-tts",
        tts_gemini_voice="Kore",
        gemini_api_key="test-key",
    )
    mock_live = MagicMock()

    with (
        patch(
            "agent_cli.agents.chat.get_llm_response",
            new_callable=AsyncMock,
        ) as mock_llm_response,
    ):
        mock_llm_response.return_value = "Hello, I'm an AI assistant."
        await _handle_conversation_turn(
            instruction="Hello",
            chat_state=chat_state,
            provider_cfg=provider_cfg,
            general_cfg=general_cfg,
            history_cfg=history_cfg,
            ollama_cfg=ollama_cfg,
            openai_llm_cfg=openai_llm_cfg,
            gemini_llm_cfg=gemini_llm_cfg,
            audio_out_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
            kokoro_tts_cfg=kokoro_tts_cfg,
            gemini_tts_cfg=gemini_tts_cfg,
            live=mock_live,
            stop_event=stop_event,
        )
        mock_llm_response.assert_awaited_once()

    # Both user and assistant messages should be added
    assert len(chat_state.conversation_history) == 2
    assert chat_state.conversation_history[0]["role"] == "user"
    assert chat_state.conversation_history[0]["content"] == "Hello"
    assert chat_state.conversation_history[1]["role"] == "assistant"
    assert chat_state.conversation_history[1]["content"] == "Hello, I'm an AI assistant."


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
            True,  # , stop
            False,  # , status
            False,  # , toggle
            quiet=False,
        )

        result = runner.invoke(app, ["chat", "--status"])
        assert result.exit_code == 0
        mock_stop_or_status.assert_called_with(
            "chat",
            "chat agent",
            False,  # , stop
            True,  # , status
            False,  # , toggle
            quiet=False,
        )


def test_chat_command_list_output_devices():
    """Test the list-output-devices flag."""
    runner = CliRunner()
    mock_vad_class = MagicMock()
    with (
        patch(
            "agent_cli.agents.chat.setup_devices",
        ) as mock_setup_devices,
        patch.dict(
            "sys.modules",
            {"agent_cli.core.vad": MagicMock(VoiceActivityDetector=mock_vad_class)},
        ),
    ):
        mock_setup_devices.return_value = None
        result = runner.invoke(app, ["chat", "--list-devices"])
        assert result.exit_code == 0
        mock_setup_devices.assert_called_once()


@pytest.mark.asyncio
async def test_async_main_exception_handling():
    """Test that exceptions in async_main are caught and logged."""
    general_cfg = config.General(log_level="INFO", log_file=None, quiet=False, list_devices=True)
    provider_cfg = config.ProviderSelection(
        asr_provider="wyoming",
        llm_provider="ollama",
        tts_provider="wyoming",
    )
    history_cfg = config.History()
    audio_in_cfg = config.AudioInput()
    wyoming_asr_cfg = config.WyomingASR(asr_wyoming_ip="localhost", asr_wyoming_port=10300)
    openai_asr_cfg = config.OpenAIASR(asr_openai_model="whisper-1")
    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model="gemini-2.0-flash",
        gemini_api_key="test-key",
    )
    ollama_cfg = config.Ollama(llm_ollama_model="test-model", llm_ollama_host="localhost")
    openai_llm_cfg = config.OpenAILLM(llm_openai_model=DEFAULT_OPENAI_MODEL, openai_base_url=None)
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model="gemini-1.5-flash",
        gemini_api_key="test-key",
    )
    audio_out_cfg = config.AudioOutput()
    wyoming_tts_cfg = config.WyomingTTS(tts_wyoming_ip="localhost", tts_wyoming_port=10200)
    openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
    kokoro_tts_cfg = config.KokoroTTS(
        tts_kokoro_model="tts-1",
        tts_kokoro_voice="alloy",
        tts_kokoro_host="http://localhost:8000/v1",
    )
    gemini_tts_cfg = config.GeminiTTS(
        tts_gemini_model="gemini-2.5-flash-preview-tts",
        tts_gemini_voice="Kore",
        gemini_api_key="test-key",
    )

    mock_vad = MagicMock()

    with (
        patch("agent_cli.agents.chat.setup_devices", side_effect=Exception("Test error")),
        patch("agent_cli.agents.chat.console") as mock_console,
    ):
        with pytest.raises(Exception, match="Test error"):
            await _async_main(
                vad=mock_vad,
                provider_cfg=provider_cfg,
                general_cfg=general_cfg,
                history_cfg=history_cfg,
                audio_in_cfg=audio_in_cfg,
                wyoming_asr_cfg=wyoming_asr_cfg,
                openai_asr_cfg=openai_asr_cfg,
                gemini_asr_cfg=gemini_asr_cfg,
                ollama_cfg=ollama_cfg,
                openai_llm_cfg=openai_llm_cfg,
                gemini_llm_cfg=gemini_llm_cfg,
                audio_out_cfg=audio_out_cfg,
                wyoming_tts_cfg=wyoming_tts_cfg,
                openai_tts_cfg=openai_tts_cfg,
                kokoro_tts_cfg=kokoro_tts_cfg,
                gemini_tts_cfg=gemini_tts_cfg,
            )
        mock_console.print_exception.assert_called_once()
