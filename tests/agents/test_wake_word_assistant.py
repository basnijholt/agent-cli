"""Tests for the wake word assistant agent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agent_cli.cli import app

runner = CliRunner()


def test_assistant_help():
    """Test the assistant --help command."""
    result = runner.invoke(app, ["assistant", "--help"])
    assert result.exit_code == 0
    assert "Usage: agent-cli assistant [OPTIONS]" in result.stdout


@patch("agent_cli.agents.assistant.asyncio.run")
def test_assistant_command(mock_asyncio_run: MagicMock):
    """Test the assistant command."""
    result = runner.invoke(app, ["assistant"])
    assert result.exit_code == 0
    mock_asyncio_run.assert_called_once()
