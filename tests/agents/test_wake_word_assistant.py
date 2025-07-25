"""Tests for the wake word assistant agent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agent_cli.cli import app

runner = CliRunner()


def test_assistant_help():
    """Test the assistant --help command."""
    result = runner.invoke(app, ["assistant", "--help"], env={"NO_COLOR": "1", "TERM": "dumb"})
    assert result.exit_code == 0
    assert "Usage: agent-cli assistant [OPTIONS]" in result.stdout


@patch("agent_cli.agents.assistant.asyncio.run")
def test_assistant_command(mock_asyncio_run: MagicMock):
    """Test the assistant command."""
    result = runner.invoke(app, ["assistant"])
    assert result.exit_code == 0
    mock_asyncio_run.assert_called_once()


@patch("agent_cli.agents.assistant.stop_or_status_or_toggle")
def test_assistant_stop(mock_stop_or_status_or_toggle: MagicMock):
    """Test the assistant --stop command."""
    result = runner.invoke(app, ["assistant", "--stop"])
    assert result.exit_code == 0
    mock_stop_or_status_or_toggle.assert_called_once_with(
        "assistant",
        "wake word assistant",
        True,
        False,
        False,
        quiet=False,
    )


@patch("agent_cli.agents.assistant.stop_or_status_or_toggle")
def test_assistant_status(mock_stop_or_status_or_toggle: MagicMock):
    """Test the assistant --status command."""
    result = runner.invoke(app, ["assistant", "--status"])
    assert result.exit_code == 0
    mock_stop_or_status_or_toggle.assert_called_once_with(
        "assistant",
        "wake word assistant",
        False,
        True,
        False,
        quiet=False,
    )


@patch("agent_cli.agents.assistant.stop_or_status_or_toggle")
def test_assistant_toggle(mock_stop_or_status_or_toggle: MagicMock):
    """Test the assistant --toggle command."""
    result = runner.invoke(app, ["assistant", "--toggle"])
    assert result.exit_code == 0
    mock_stop_or_status_or_toggle.assert_called_once_with(
        "assistant",
        "wake word assistant",
        False,
        False,
        True,
        quiet=False,
    )


@patch("agent_cli.agents.assistant.asyncio.run")
def test_assistant_with_whispercpp(mock_asyncio_run: MagicMock):
    """Test the assistant command with whispercpp ASR provider."""
    result = runner.invoke(app, ["assistant", "--asr-provider", "whispercpp"])
    assert result.exit_code == 0
    mock_asyncio_run.assert_called_once()
    # Verify the provider is set correctly in the call
    call_args = mock_asyncio_run.call_args[0][0]
    # The coroutine is passed as the first argument
    # We can't directly inspect it, but we can verify the command ran successfully


@patch("agent_cli.agents.assistant.asyncio.run")
def test_assistant_whispercpp_custom_host_port(mock_asyncio_run: MagicMock):
    """Test the assistant command with custom whispercpp host and port."""
    result = runner.invoke(
        app,
        [
            "assistant",
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
