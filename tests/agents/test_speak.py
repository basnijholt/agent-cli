"""Tests for the speak agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from agent_cli.cli import app

runner = CliRunner()


@patch("agent_cli.agents.speak._async_main", new_callable=AsyncMock)
def test_speak_agent(mock_async_main: AsyncMock) -> None:
    """Test the speak agent."""
    result = runner.invoke(app, ["speak", "hello"], catch_exceptions=False)
    assert result.exit_code == 0
    mock_async_main.assert_called_once()


@patch("agent_cli.agents.speak.process_manager.kill_process")
def test_speak_stop(mock_kill_process: MagicMock) -> None:
    """Test the --stop flag."""
    mock_kill_process.return_value = True
    result = runner.invoke(app, ["speak", "--stop"])
    assert result.exit_code == 0
    assert "Speak process stopped" in result.stdout
    mock_kill_process.assert_called_once_with("speak")


@patch("agent_cli.agents.speak.process_manager.kill_process")
def test_speak_stop_not_running(mock_kill_process: MagicMock) -> None:
    """Test the --stop flag when the process is not running."""
    mock_kill_process.return_value = False
    result = runner.invoke(app, ["speak", "--stop"])
    assert result.exit_code == 0
    assert "No speak process is running" in result.stdout


@patch("agent_cli.agents.speak.process_manager.is_process_running")
def test_speak_status_running(mock_is_process_running: MagicMock) -> None:
    """Test the --status flag when the process is running."""
    mock_is_process_running.return_value = True
    with patch("agent_cli.agents.speak.process_manager.read_pid_file", return_value=123):
        result = runner.invoke(app, ["speak", "--status"])
    assert result.exit_code == 0
    assert "Speak process is running" in result.stdout


@patch("agent_cli.agents.speak.process_manager.is_process_running")
def test_speak_status_not_running(mock_is_process_running: MagicMock) -> None:
    """Test the --status flag when the process is not running."""
    mock_is_process_running.return_value = False
    result = runner.invoke(app, ["speak", "--status"])
    assert result.exit_code == 0
    assert "Speak process is not running" in result.stdout
