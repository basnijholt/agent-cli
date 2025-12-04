"""Tests for the speak agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from agent_cli import config
from agent_cli.agents.speak import _async_main
from agent_cli.cli import app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


@pytest.mark.asyncio
async def test_async_main_with_text():
    """Test the _async_main function with text provided."""
    general_cfg = config.General(log_level="INFO", quiet=True)
    provider_cfg = config.ProviderSelection(
        tts_provider="wyoming",
        llm_provider="ollama",
        asr_provider="wyoming",
    )
    audio_out_cfg = config.AudioOutput(enable_tts=True)
    wyoming_tts_cfg = config.WyomingTTS(tts_wyoming_ip="localhost", tts_wyoming_port=10200)
    openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
    kokoro_tts_cfg = config.KokoroTTS(
        tts_kokoro_model="tts-1",
        tts_kokoro_voice="alloy",
        tts_kokoro_host="http://localhost:8000/v1",
    )

    with (
        patch(
            "agent_cli.agents.speak.setup_devices",
            return_value=(None, None, 1),
        ),
        patch(
            "agent_cli.agents.speak.handle_tts_playback",
            new_callable=AsyncMock,
        ) as mock_handle_tts,
    ):
        await _async_main(
            general_cfg=general_cfg,
            text="hello",
            provider_cfg=provider_cfg,
            audio_out_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
            kokoro_tts_cfg=kokoro_tts_cfg,
        )
        mock_handle_tts.assert_called_once()


@pytest.mark.asyncio
async def test_async_main_no_devices():
    """Test the _async_main function when no devices are found."""
    general_cfg = config.General(log_level="INFO", quiet=True)
    provider_cfg = config.ProviderSelection(
        tts_provider="wyoming",
        llm_provider="ollama",
        asr_provider="wyoming",
    )
    audio_out_cfg = config.AudioOutput(enable_tts=True)
    wyoming_tts_cfg = config.WyomingTTS(tts_wyoming_ip="localhost", tts_wyoming_port=10200)
    openai_tts_cfg = config.OpenAITTS(tts_openai_model="tts-1", tts_openai_voice="alloy")
    kokoro_tts_cfg = config.KokoroTTS(
        tts_kokoro_model="tts-1",
        tts_kokoro_voice="alloy",
        tts_kokoro_host="http://localhost:8000/v1",
    )

    with (
        patch(
            "agent_cli.agents.speak.setup_devices",
            return_value=None,
        ) as mock_setup,
        patch(
            "agent_cli.agents.speak.handle_tts_playback",
            new_callable=AsyncMock,
        ) as mock_handle_tts,
    ):
        await _async_main(
            general_cfg=general_cfg,
            text="hello",
            provider_cfg=provider_cfg,
            audio_out_cfg=audio_out_cfg,
            wyoming_tts_cfg=wyoming_tts_cfg,
            openai_tts_cfg=openai_tts_cfg,
            kokoro_tts_cfg=kokoro_tts_cfg,
        )
        mock_setup.assert_called_once()
        mock_handle_tts.assert_not_called()


@patch("agent_cli.agents.speak._async_main", new_callable=AsyncMock)
def test_speak_agent(mock_async_main: AsyncMock) -> None:
    """Test the speak agent."""
    result = runner.invoke(app, ["speak", "hello"], catch_exceptions=False)
    assert result.exit_code == 0
    mock_async_main.assert_called_once()


@patch("agent_cli.agents.speak.process.kill_process")
def test_speak_stop(mock_kill_process: MagicMock) -> None:
    """Test the --stop flag."""
    mock_kill_process.return_value = True
    result = runner.invoke(app, ["speak", "--stop"])
    assert result.exit_code == 0
    assert "Speak process stopped" in result.stdout
    mock_kill_process.assert_called_once_with("speak")


@patch("agent_cli.agents.speak.process.kill_process")
def test_speak_stop_not_running(mock_kill_process: MagicMock) -> None:
    """Test the --stop flag when the process is not running."""
    mock_kill_process.return_value = False
    result = runner.invoke(app, ["speak", "--stop"])
    assert result.exit_code == 0
    assert "No speak process is running" in result.stdout


@patch("agent_cli.agents.speak.process.is_process_running")
def test_speak_status_running(mock_is_process_running: MagicMock) -> None:
    """Test the --status flag when the process is running."""
    mock_is_process_running.return_value = True
    with patch("agent_cli.agents.speak.process.read_pid_file", return_value=123):
        result = runner.invoke(app, ["speak", "--status"])
    assert result.exit_code == 0
    assert "Speak process is running" in result.stdout


@patch("agent_cli.agents.speak.process.is_process_running")
def test_speak_status_not_running(mock_is_process_running: MagicMock) -> None:
    """Test the --status flag when the process is not running."""
    mock_is_process_running.return_value = False
    result = runner.invoke(app, ["speak", "--status"])
    assert result.exit_code == 0
    assert "Speak process is not running" in result.stdout
