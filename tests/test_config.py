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
    """Provides a config file with the new flat, dashed-key format."""
    config_content = """
[defaults]
log-level = "INFO"
llm-provider = "local"
ollama-model = "default-local-model"
ollama-host = "http://localhost:11434"
openai-llm-model = "default-openai-model"
openai-api-key = "default-key"

[autocorrect]
llm-provider = "openai"
quiet = true
openai-llm-model = "autocorrect-openai-model"
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_content)
    return config_path


def test_config_loader_key_replacement(config_file: Path) -> None:
    """Test that dashed keys are replaced with underscores."""
    config = load_config(str(config_file))
    # Check a value from [defaults]
    assert config["defaults"]["log_level"] == "INFO"
    # Check a value from [autocorrect]
    assert config["autocorrect"]["llm_provider"] == "openai"
    assert config["autocorrect"]["openai_llm_model"] == "autocorrect-openai-model"


def test_set_config_defaults(config_file: Path) -> None:
    """Test the set_config_defaults function with the new flat config."""
    mock_autocorrect_cmd = Command(name="autocorrect")
    mock_main_command = MagicMock()
    mock_main_command.commands = {"autocorrect": mock_autocorrect_cmd}
    ctx = Context(command=mock_main_command)

    # Test with no subcommand (should only load defaults)
    ctx.invoked_subcommand = None
    set_config_defaults(ctx, str(config_file))
    expected_defaults = {
        "log_level": "INFO",
        "llm_provider": "local",
        "ollama_model": "default-local-model",
        "ollama_host": "http://localhost:11434",
        "openai_llm_model": "default-openai-model",
        "openai_api_key": "default-key",
    }
    assert ctx.default_map == expected_defaults

    # Test with autocorrect subcommand (should merge defaults)
    ctx.invoked_subcommand = "autocorrect"
    ctx.default_map = {}  # Reset
    set_config_defaults(ctx, str(config_file))

    # Check combined defaults: [autocorrect] overrides [defaults]
    expected_merged_defaults = {
        "log_level": "INFO",
        "llm_provider": "openai",  # Overridden by [autocorrect]
        "ollama_model": "default-local-model",
        "ollama_host": "http://localhost:11434",
        "openai_llm_model": "autocorrect-openai-model",  # Overridden by [autocorrect]
        "openai_api_key": "default-key",
        "quiet": True,  # Added by [autocorrect]
    }
    assert ctx.default_map == expected_merged_defaults


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
        assert config["defaults"]["log_level"] == "INFO"

    mock_path1.exists.return_value = True
    mock_path2.exists.return_value = True
    with config_file.open("rb") as f:
        mock_path1.open.return_value.__enter__.return_value = f
        config = load_config(None)
        assert config["defaults"]["log_level"] == "INFO"
