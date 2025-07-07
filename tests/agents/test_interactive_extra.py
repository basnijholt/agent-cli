"""Tests for the interactive agent."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from agent_cli.agents.interactive import (
    ASRConfig,
    FileConfig,
    GeneralConfig,
    LLMConfig,
    TTSConfig,
    _handle_conversation_turn,
    _setup_output_device,
    async_main,
)
from agent_cli.cli import app
from agent_cli.utils import InteractiveStopEvent


def test_setup_output_device():
    """Test the _setup_output_device function."""
    mock_p = MagicMock()
    mock_p.get_device_info_by_index.return_value = {"name": "Test Output Device"}

    with (
        patch("agent_cli.audio.output_device", return_value=(0, "Test Output Device")),
        patch("agent_cli.utils.console") as mock_console,
    ):
        input_device_index, input_device_name = _setup_output_device(
            mock_p,
            quiet=False,
            input_device_name="Test Output Device",
            input_device_index=0,
        )

    assert input_device_index == 0
    assert input_device_name == "Test Output Device"
    mock_console.print.assert_called_once()


@pytest.mark.asyncio
async def test_handle_conversation_turn_no_instruction():
    """Test that the conversation turn exits early if no instruction is given."""
    mock_p = MagicMock()
    stop_event = InteractiveStopEvent()
    conversation_history = []
    general_cfg = GeneralConfig(log_level="INFO", log_file=None, quiet=True)
    asr_config = ASRConfig(
        server_ip="localhost",
        server_port=10300,
        input_device_index=None,
        input_device_name=None,
        list_input_devices=False,
    )
    llm_config = LLMConfig(model="test-model", ollama_host="localhost")
    tts_config = TTSConfig(
        enabled=False,
        server_ip="localhost",
        server_port=10200,
        voice_name=None,
        language=None,
        speaker=None,
        output_device_index=None,
        output_device_name=None,
        list_output_devices=False,
        speed=1.0,
    )
    file_config = FileConfig(save_file=None, history_dir=None)
    mock_live = MagicMock()

    with patch(
        "agent_cli.agents.interactive.asr.transcribe_live_audio",
        return_value="",
    ) as mock_transcribe:
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
        mock_transcribe.assert_awaited_once()
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
        patch(
            "agent_cli.agents.interactive.list_output_devices",
        ) as mock_list_output_devices,
        patch(
            "agent_cli.agents.interactive.pyaudio_context",
        ) as mock_pyaudio_context,
    ):
        result = runner.invoke(app, ["interactive", "--list-output-devices"])
        assert result.exit_code == 0
        mock_pyaudio_context.assert_called_once()
        mock_list_output_devices.assert_called_once()


@pytest.mark.asyncio
async def test_async_main_exception_handling():
    """Test that exceptions in async_main are caught and logged."""
    general_cfg = GeneralConfig(log_level="INFO", log_file=None, quiet=False)
    asr_config = ASRConfig(
        server_ip="localhost",
        server_port=10300,
        input_device_index=None,
        input_device_name=None,
        list_input_devices=True,
    )  # To trigger an early exit
    llm_config = LLMConfig(model="test-model", ollama_host="localhost")
    tts_config = TTSConfig(
        enabled=False,
        server_ip="localhost",
        server_port=10200,
        voice_name=None,
        language=None,
        speaker=None,
        output_device_index=None,
        output_device_name=None,
        list_output_devices=False,
        speed=1.0,
    )
    file_config = FileConfig(save_file=None, history_dir=None)

    with (
        patch(
            "agent_cli.agents.interactive.pyaudio_context",
            side_effect=Exception("Test error"),
        ),
        patch("agent_cli.agents.interactive.console") as mock_console,
    ):
        with pytest.raises(Exception, match="Test error"):
            await async_main(
                general_cfg=general_cfg,
                asr_config=asr_config,
                llm_config=llm_config,
                tts_config=tts_config,
                file_config=file_config,
            )
        mock_console.print_exception.assert_called_once()
