"""Tests for the CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from typer.testing import CliRunner

from agent_cli.cli import app

if TYPE_CHECKING:
    import pytest

runner = CliRunner()


def test_main_no_args() -> None:
    """Test the main function with no arguments."""
    result = runner.invoke(app)
    assert "No command specified" in result.stdout
    assert "Usage" in result.stdout


@patch("agent_cli.core.utils.setup_logging")
def test_main_with_args(mock_setup_logging: pytest.MagicMock) -> None:
    """Test the main function with arguments."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
    mock_setup_logging.assert_not_called()


@patch("agent_cli.agents.server.run_server")
def test_server_command(mock_run_server: pytest.MagicMock) -> None:
    """Test the server command."""
    result = runner.invoke(app, ["server"])
    assert result.exit_code == 0
    assert "Starting Agent CLI transcription server" in result.stdout
    mock_run_server.assert_called_once_with(host="0.0.0.0", port=61337, reload=False)  # noqa: S104


@patch("agent_cli.agents.server.run_server")
def test_server_command_with_options(mock_run_server: pytest.MagicMock) -> None:
    """Test the server command with custom options."""
    result = runner.invoke(app, ["server", "--host", "127.0.0.1", "--port", "8080", "--reload"])
    assert result.exit_code == 0
    assert "Starting Agent CLI transcription server on 127.0.0.1:8080" in result.stdout
    assert "Auto-reload enabled for development" in result.stdout
    mock_run_server.assert_called_once_with(host="127.0.0.1", port=8080, reload=True)
