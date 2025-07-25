"""Tests for the chat agent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agent_cli.cli import app

runner = CliRunner()


def test_chat_help():
    """Test the chat --help command."""
    result = runner.invoke(app, ["chat", "--help"], env={"NO_COLOR": "1", "TERM": "dumb"})
    assert result.exit_code == 0
    assert "Usage: agent-cli chat [OPTIONS]" in result.stdout


@patch("agent_cli.agents.chat.asyncio.run")
def test_chat_command(mock_asyncio_run: MagicMock):
    """Test the chat command."""
    result = runner.invoke(app, ["chat"])
    assert result.exit_code == 0
    mock_asyncio_run.assert_called_once()


@patch("agent_cli.agents.chat.stop_or_status_or_toggle")
def test_chat_stop(mock_stop_or_status_or_toggle: MagicMock):
    """Test the chat --stop command."""
    result = runner.invoke(app, ["chat", "--stop"])
    assert result.exit_code == 0
    mock_stop_or_status_or_toggle.assert_called_once_with(
        "chat",
        "chat agent",
        True,
        False,
        False,
        quiet=False,
    )


@patch("agent_cli.agents.chat.stop_or_status_or_toggle")
def test_chat_status(mock_stop_or_status_or_toggle: MagicMock):
    """Test the chat --status command."""
    result = runner.invoke(app, ["chat", "--status"])
    assert result.exit_code == 0
    mock_stop_or_status_or_toggle.assert_called_once_with(
        "chat",
        "chat agent",
        False,
        True,
        False,
        quiet=False,
    )


@patch("agent_cli.agents.chat.stop_or_status_or_toggle")
def test_chat_toggle(mock_stop_or_status_or_toggle: MagicMock):
    """Test the chat --toggle command."""
    result = runner.invoke(app, ["chat", "--toggle"])
    assert result.exit_code == 0
    mock_stop_or_status_or_toggle.assert_called_once_with(
        "chat",
        "chat agent",
        False,
        False,
        True,
        quiet=False,
    )


@patch("agent_cli.agents.chat.asyncio.run")
def test_chat_with_whispercpp(mock_asyncio_run: MagicMock):
    """Test the chat command with whispercpp ASR provider."""
    result = runner.invoke(app, ["chat", "--asr-provider", "whispercpp"])
    assert result.exit_code == 0
    mock_asyncio_run.assert_called_once()


@patch("agent_cli.agents.chat.asyncio.run")
def test_chat_whispercpp_custom_host_port(mock_asyncio_run: MagicMock):
    """Test the chat command with custom whispercpp host and port."""
    result = runner.invoke(
        app,
        [
            "chat",
            "--asr-provider",
            "whispercpp",
            "--asr-whispercpp-host",
            "192.168.1.100",
            "--asr-whispercpp-port",
            "10500",
        ],
    )
    assert result.exit_code == 0
    mock_asyncio_run.assert_called_once()


@patch("agent_cli.agents.chat.asyncio.run")
def test_chat_with_custom_history_options(mock_asyncio_run: MagicMock):
    """Test the chat command with custom history options."""
    result = runner.invoke(
        app,
        [
            "chat",
            "--history-dir",
            "/tmp/test-history",
            "--last-n-messages",
            "100",
        ],
    )
    assert result.exit_code == 0
    mock_asyncio_run.assert_called_once()
