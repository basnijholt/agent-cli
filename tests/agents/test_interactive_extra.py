"""Tests for the interactive agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from agent_cli.agents._config import (
    ASRConfig,
    FileConfig,
    GeneralConfig,
    LLMConfig,
    OllamaLLMConfig,
    OpenAIASRConfig,
    OpenAILLMConfig,
    OpenAITTSConfig,
    TTSConfig,
    WyomingASRConfig,
    WyomingTTSConfig,
)
from agent_cli.agents.interactive import (
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
    general_cfg = GeneralConfig(log_level="INFO", log_file=None, quiet=True, list_devices=True)
    asr_config = ASRConfig(
        provider="local",
        input_device_index=None,
        input_device_name=None,
        providers={
            "local": WyomingASRConfig(server_ip="localhost", server_port=10300),
            "openai": OpenAIASRConfig(api_key=None),
        },
    )
    llm_config = LLMConfig(
        provider="local",
        providers={
            "local": OllamaLLMConfig(model="test-model", host="localhost"),
            "openai": OpenAILLMConfig(model="gpt-4o-mini", api_key=None),
        },
    )
    tts_config = TTSConfig(
        enabled=False,
        provider="local",
        output_device_index=None,
        output_device_name=None,
        speed=1.0,
        providers={
            "local": WyomingTTSConfig(
                server_ip="localhost",
                server_port=10200,
                voice_name=None,
                language=None,
                speaker=None,
            ),
            "openai": OpenAITTSConfig(api_key=None),
        },
    )
    file_config = FileConfig(save_file=None, history_dir=None)
    mock_live = MagicMock()

    with patch("agent_cli.agents.interactive.asr.get_transcriber") as mock_get_transcriber:
        mock_transcriber = AsyncMock(return_value="")
        mock_get_transcriber.return_value = mock_transcriber
        await _handle_conversation_turn(
            p=mock_p,
            stop_event=stop_event,
            conversation_history=conversation_history,
            general_cfg=general_cfg,
            asr_config=asr_config,
            llm_config=llm_config,
            tts_config=tts_config,
            file_config=file_config,
            live=mock_live,
        )
        mock_get_transcriber.assert_called_once()
        mock_transcriber.assert_awaited_once()
    assert not conversation_history


def test_interactive_command_stop_and_status():
    """Test the stop and status flags of the interactive command."""
    runner = CliRunner()
    with patch(
        "agent_cli.agents.interactive.stop_or_status_or_toggle",
        return_value=True,
    ) as mock_stop_or_status:
        result = runner.invoke(app, ["interactive", "--stop"])
        assert result.exit_code == 0
        mock_stop_or_status.assert_called_with(
            "interactive",
            "interactive agent",
            True,  # noqa: FBT003, stop
            False,  # noqa: FBT003, status
            False,  # noqa: FBT003, toggle
            quiet=False,
        )

        result = runner.invoke(app, ["interactive", "--status"])
        assert result.exit_code == 0
        mock_stop_or_status.assert_called_with(
            "interactive",
            "interactive agent",
            False,  # noqa: FBT003, stop
            True,  # noqa: FBT003, status
            False,  # noqa: FBT003, toggle
            quiet=False,
        )


def test_interactive_command_list_output_devices():
    """Test the list-output-devices flag."""
    runner = CliRunner()
    with (
        patch("agent_cli.agents.interactive.setup_devices") as mock_setup_devices,
        patch("agent_cli.agents.interactive.pyaudio_context") as mock_pyaudio_context,
    ):
        mock_setup_devices.return_value = None
        result = runner.invoke(app, ["interactive", "--list-devices"])
        assert result.exit_code == 0
        mock_pyaudio_context.assert_called_once()
        mock_setup_devices.assert_called_once()


@pytest.mark.asyncio
async def test_async_main_exception_handling():
    """Test that exceptions in async_main are caught and logged."""
    general_cfg = GeneralConfig(log_level="INFO", log_file=None, quiet=False, list_devices=True)
    asr_config = ASRConfig(
        provider="local",
        input_device_index=None,
        input_device_name=None,
        providers={
            "local": WyomingASRConfig(server_ip="localhost", server_port=10300),
            "openai": OpenAIASRConfig(api_key=None),
        },
    )  # To trigger an early exit
    llm_config = LLMConfig(
        provider="local",
        providers={
            "local": OllamaLLMConfig(model="test-model", host="localhost"),
            "openai": OpenAILLMConfig(model="gpt-4o-mini", api_key=None),
        },
    )
    tts_config = TTSConfig(
        enabled=False,
        provider="local",
        output_device_index=None,
        output_device_name=None,
        speed=1.0,
        providers={
            "local": WyomingTTSConfig(
                server_ip="localhost",
                server_port=10200,
                voice_name=None,
                language=None,
                speaker=None,
            ),
            "openai": OpenAITTSConfig(api_key=None),
        },
    )
    file_config = FileConfig(save_file=None, history_dir=None)

    with (
        patch("agent_cli.agents.interactive.pyaudio_context", side_effect=Exception("Test error")),
        patch("agent_cli.agents.interactive.console") as mock_console,
    ):
        with pytest.raises(Exception, match="Test error"):
            await _async_main(
                general_cfg=general_cfg,
                asr_config=asr_config,
                llm_config=llm_config,
                tts_config=tts_config,
                file_config=file_config,
            )
        mock_console.print_exception.assert_called_once()
