"""Tests for the transcribe agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from agent_cli.cli import app

runner = CliRunner()


@patch("agent_cli.agents.transcribe.asr.transcribe_audio", new_callable=AsyncMock)
@patch("agent_cli.agents.transcribe.process_manager.pid_file_context")
def test_transcribe_agent(
    mock_pid_context: MagicMock,
    mock_transcribe_audio: AsyncMock,
) -> None:
    """Test the transcribe agent."""
    mock_transcribe_audio.return_value = "hello"
    result = runner.invoke(app, ["transcribe"])
    assert result.exit_code == 0
    mock_pid_context.assert_called_once_with("transcribe")
    mock_transcribe_audio.assert_called_once()


@patch("agent_cli.agents.transcribe.process_manager.kill_process")
def test_transcribe_stop(mock_kill_process: MagicMock) -> None:
    """Test the --stop flag."""
    mock_kill_process.return_value = True
    result = runner.invoke(app, ["transcribe", "--stop"])
    assert result.exit_code == 0
    assert "Transcribe stopped" in result.stdout
    mock_kill_process.assert_called_once_with("transcribe")


@patch("agent_cli.agents.transcribe.process_manager.kill_process")
def test_transcribe_stop_not_running(mock_kill_process: MagicMock) -> None:
    """Test the --stop flag when the process is not running."""
    mock_kill_process.return_value = False
    result = runner.invoke(app, ["transcribe", "--stop"])
    assert result.exit_code == 0
    assert "No transcribe is running" in result.stdout


@patch("agent_cli.agents.transcribe.process_manager.is_process_running")
def test_transcribe_status_running(mock_is_process_running: MagicMock) -> None:
    """Test the --status flag when the process is running."""
    mock_is_process_running.return_value = True
    with patch("agent_cli.agents.transcribe.process_manager.read_pid_file", return_value=123):
        result = runner.invoke(app, ["transcribe", "--status"])
    assert result.exit_code == 0
    assert "Transcribe is running" in result.stdout


@patch("agent_cli.agents.transcribe.process_manager.is_process_running")
def test_transcribe_status_not_running(mock_is_process_running: MagicMock) -> None:
    """Test the --status flag when the process is not running."""
    mock_is_process_running.return_value = False
    result = runner.invoke(app, ["transcribe", "--status"])
    assert result.exit_code == 0
    assert "Transcribe is not running" in result.stdout
