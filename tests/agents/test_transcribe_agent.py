"""Tests for the transcribe agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from agent_cli.cli import app

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


@patch("agent_cli.agents.transcribe.asr.create_transcriber")
@patch("agent_cli.agents.transcribe.process.pid_file_context")
@patch("agent_cli.agents.transcribe.setup_devices")
def test_transcribe_agent(
    mock_setup_devices: MagicMock,
    mock_pid_context: MagicMock,
    mock_create_transcriber: MagicMock,
) -> None:
    """Test the transcribe agent."""
    mock_transcriber = AsyncMock(return_value="hello")
    mock_create_transcriber.return_value = mock_transcriber
    mock_setup_devices.return_value = (0, "mock_device", None)
    with patch("pyperclip.copy") as mock_copy, patch("pyperclip.paste", return_value=""):
        result = runner.invoke(
            app,
            [
                "transcribe",
                "--asr-provider",
                "wyoming",
                "--openai-api-key",
                "test",
            ],
        )
    assert result.exit_code == 0, result.output
    mock_pid_context.assert_called_once()
    mock_create_transcriber.assert_called_once()
    mock_transcriber.assert_called_once()
    mock_copy.assert_called_once_with("hello")


@patch("agent_cli.agents.transcribe.process.kill_process")
def test_transcribe_stop(mock_kill_process: MagicMock) -> None:
    """Test the --stop flag."""
    mock_kill_process.return_value = True
    result = runner.invoke(app, ["transcribe", "--stop"])
    assert result.exit_code == 0
    assert "Transcribe stopped" in result.stdout
    mock_kill_process.assert_called_once_with("transcribe")


@patch("agent_cli.agents.transcribe.process.kill_process")
def test_transcribe_stop_not_running(mock_kill_process: MagicMock) -> None:
    """Test the --stop flag when the process is not running."""
    mock_kill_process.return_value = False
    result = runner.invoke(app, ["transcribe", "--stop"])
    assert result.exit_code == 0
    assert "No transcribe is running" in result.stdout


@patch("agent_cli.agents.transcribe.process.is_process_running")
def test_transcribe_status_running(mock_is_process_running: MagicMock) -> None:
    """Test the --status flag when the process is running."""
    mock_is_process_running.return_value = True
    with patch("agent_cli.agents.transcribe.process.read_pid_file", return_value=123):
        result = runner.invoke(app, ["transcribe", "--status"])
    assert result.exit_code == 0
    assert "Transcribe is running" in result.stdout


@patch("agent_cli.agents.transcribe.process.is_process_running")
def test_transcribe_status_not_running(mock_is_process_running: MagicMock) -> None:
    """Test the --status flag when the process is not running."""
    mock_is_process_running.return_value = False
    result = runner.invoke(app, ["transcribe", "--status"])
    assert result.exit_code == 0
    assert "Transcribe is not running" in result.stdout
