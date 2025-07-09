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
