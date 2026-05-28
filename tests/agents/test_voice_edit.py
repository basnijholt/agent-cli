"""Tests for the voice assistant agent."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agent_cli.cli import app
from agent_cli.core import process

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


@patch("agent_cli.agents.voice_edit._async_main", return_value=None)
@patch("agent_cli.agents.voice_edit.asyncio.run")
@patch("agent_cli.agents.voice_edit.process.pid_file_context")
def test_voice_edit_agent(
    mock_pid_ctx: MagicMock,
    mock_run: MagicMock,
    mock_async_main: MagicMock,
) -> None:
    """Test the voice assistant agent."""
    mock_pid_ctx.return_value.__enter__.return_value = None
    with runner.isolated_filesystem():
        # Provide a real config file to satisfy CLI preflight.
        Path("config.toml").write_text("", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "voice-edit",
                "--config",
                "config.toml",
                "--llm-provider",
                "ollama",
                "--asr-provider",
                "wyoming",
                "--tts-provider",
                "wyoming",
                "--openai-api-key",
                "test",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_run.assert_called_once()
    mock_async_main.assert_called_once()


@patch("agent_cli.agents.voice_edit.process.stop_process")
def test_voice_edit_stop(mock_stop_process: MagicMock) -> None:
    """Test the --stop flag."""
    mock_stop_process.return_value = process.StopProcessResult(
        process_name="voice-edit",
        was_running=True,
        status=process.ProcessStatus("voice-edit", running=False, pid=None),
        stale_cleaned=False,
    )
    result = runner.invoke(app, ["voice-edit", "--stop"])
    assert result.exit_code == 0
    assert "Voice assistant stopped" in result.stdout
    mock_stop_process.assert_called_once_with("voice-edit", wait_for_start_seconds=0.0)


@patch("agent_cli.agents.voice_edit.process.stop_process")
def test_voice_edit_stop_not_running(mock_stop_process: MagicMock) -> None:
    """Test the --stop flag when the process is not running."""
    mock_stop_process.return_value = process.StopProcessResult(
        process_name="voice-edit",
        was_running=False,
        status=process.ProcessStatus("voice-edit", running=False, pid=None),
        stale_cleaned=False,
    )
    result = runner.invoke(app, ["voice-edit", "--stop"])
    assert result.exit_code == 0
    assert "No voice assistant is running" in result.stdout


@patch("agent_cli.agents.voice_edit.process.get_process_status")
def test_voice_edit_status_running(mock_get_process_status: MagicMock) -> None:
    """Test the --status flag when the process is running."""
    mock_get_process_status.return_value = process.ProcessStatus(
        "voice-edit",
        running=True,
        pid=123,
    )
    result = runner.invoke(app, ["voice-edit", "--status"])
    assert result.exit_code == 0
    assert "Voice assistant is running" in result.stdout


@patch("agent_cli.agents.voice_edit.process.get_process_status")
def test_voice_edit_status_not_running(mock_get_process_status: MagicMock) -> None:
    """Test the --status flag when the process is not running."""
    mock_get_process_status.return_value = process.ProcessStatus(
        "voice-edit",
        running=False,
        pid=None,
    )
    result = runner.invoke(app, ["voice-edit", "--status"])
    assert result.exit_code == 0
    assert "Voice assistant is not running" in result.stdout
