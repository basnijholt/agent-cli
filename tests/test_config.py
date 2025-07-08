"""Test the config loading."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from click import Command
from typer import Context
from typer.testing import CliRunner

from agent_cli.cli import set_config_defaults
from agent_cli.config_loader import load_config

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    config_content = """
[defaults]
log_level = "INFO"
llm_provider = "local"

[llm.local]
model = "default-local-model"
host = "http://localhost:11434"

[llm.openai]
model = "default-openai-model"
api_key = "default-key"

[autocorrect]
llm_provider = "openai"
quiet = true

[autocorrect.llm.openai]
model = "autocorrect-openai-model"
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_content)
    return config_path


def test_config_loader_basic(config_file: Path) -> None:
    """Test the config loader function directly."""
    config = load_config(str(config_file))
    assert config["defaults"]["log_level"] == "INFO"
    assert config["llm"]["local"]["model"] == "default-local-model"
    assert config["autocorrect"]["llm_provider"] == "openai"
    assert config["autocorrect"]["llm"]["openai"]["model"] == "autocorrect-openai-model"


def test_config_loader_key_replacement(config_file: Path) -> None:
    """Test that dashed keys are replaced with underscores."""
    # Add a config with dashed keys
    config_content = """
[defaults]
log-level = "DEBUG"
ollama-host = "http://example.com"

[test-command]
some-option = "value"
"""
    config_path = config_file.parent / "dashed-config.toml"
    config_path.write_text(config_content)

    config = load_config(str(config_path))
    assert config["defaults"]["log_level"] == "DEBUG"
    assert config["defaults"]["ollama_host"] == "http://example.com"
    assert config["test_command"]["some_option"] == "value"


def test_set_config_defaults(config_file: Path) -> None:
    """Test the set_config_defaults function."""
    mock_autocorrect_cmd = Command(name="autocorrect")
    mock_main_command = MagicMock()
    mock_main_command.commands = {"autocorrect": mock_autocorrect_cmd}
    ctx = Context(command=mock_main_command)

    # Test with no subcommand (should only load defaults)
    ctx.invoked_subcommand = None
    set_config_defaults(ctx, str(config_file))
    assert ctx.default_map == {"log_level": "INFO", "llm_provider": "local"}

    # Test with autocorrect subcommand
    ctx.invoked_subcommand = "autocorrect"
    ctx.default_map = {}  # Reset
    set_config_defaults(ctx, str(config_file))

    # Check combined defaults
    expected_defaults = {
        "log_level": "INFO",
        "llm_provider": "openai",
        "quiet": True,
        "llm": {"openai": {"model": "autocorrect-openai-model"}},
    }
    assert ctx.default_map == expected_defaults


@patch("agent_cli.config_loader.CONFIG_PATH")
@patch("agent_cli.config_loader.CONFIG_PATH_2")
def test_default_config_paths(
    mock_path2: MagicMock,
    mock_path1: MagicMock,
    config_file: Path,
) -> None:
    """Test that default config paths are checked in order."""
    mock_path1.exists.return_value = False
    mock_path2.exists.return_value = False
    assert load_config(None) == {}

    mock_path1.exists.return_value = False
    mock_path2.exists.return_value = True
    with config_file.open("rb") as f:
        mock_path2.open.return_value.__enter__.return_value = f
        config = load_config(None)
        assert config["llm"]["local"]["model"] == "default-local-model"

    mock_path1.exists.return_value = True
    mock_path2.exists.return_value = True
    with config_file.open("rb") as f:
        mock_path1.open.return_value.__enter__.return_value = f
        config = load_config(None)
        assert config["llm"]["local"]["model"] == "default-local-model"


@patch("agent_cli.config_loader.console")
def test_config_file_error_handling(mock_console: MagicMock, tmp_path: Path) -> None:
    """Test config loading with invalid TOML."""
    invalid_toml = tmp_path / "invalid.toml"
    invalid_toml.write_text("invalid toml content [[[")

    config = load_config(str(invalid_toml))

    assert config == {}
    mock_console.print.assert_called_once()
