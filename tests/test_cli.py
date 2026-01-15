"""Tests for the CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from typer.testing import CliRunner

from agent_cli.cli import app

if TYPE_CHECKING:
    import pytest

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


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


def test_server_command() -> None:
    """Test the server command shows subcommands."""
    result = runner.invoke(app, ["server", "--help"])
    assert result.exit_code == 0
    assert "whisper" in result.stdout
    assert "proxy" in result.stdout


@patch("uvicorn.run")
def test_server_proxy_command(mock_uvicorn_run: pytest.MagicMock) -> None:
    """Test the server proxy command."""
    result = runner.invoke(app, ["server", "proxy", "--port", "61337"])
    assert result.exit_code == 0
    assert "Starting Agent CLI transcription proxy" in result.stdout
    mock_uvicorn_run.assert_called_once()


@patch("uvicorn.run")
def test_server_proxy_command_with_options(mock_uvicorn_run: pytest.MagicMock) -> None:
    """Test the server proxy command with custom options."""
    result = runner.invoke(
        app,
        ["server", "proxy", "--host", "127.0.0.1", "--port", "8080", "--reload"],
    )
    assert result.exit_code == 0
    assert "Starting Agent CLI transcription proxy on 127.0.0.1:8080" in result.stdout
    assert "Auto-reload enabled for development" in result.stdout
    mock_uvicorn_run.assert_called_once()
