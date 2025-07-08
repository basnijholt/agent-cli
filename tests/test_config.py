"""Test the config loading."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from click import Command, Option
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

[llm.local]
model = "wildcard-model"

[autocorrect.llm.local]
model = "autocorrect-model"

[autocorrect.general]
quiet = true

[transcribe.llm.local]
model = "transcribe-model"

[transcribe.general]
clipboard = false
"""
    config_path = tmp_path / "config.toml"
    config_path.write_text(config_content)
    return config_path


def test_config_loader_basic(config_file: Path) -> None:
    """Test the config loader function directly."""
    # Test loading from explicit path
    config = load_config(str(config_file))
    assert config["llm"]["local"]["model"] == "wildcard-model"
    assert config["defaults"]["log_level"] == "INFO"
    assert config["autocorrect"]["llm"]["local"]["model"] == "autocorrect-model"
    assert config["autocorrect"]["general"]["quiet"] is True
    assert config["transcribe"]["llm"]["local"]["model"] == "transcribe-model"
    assert config["transcribe"]["general"]["clipboard"] is False

    # Test loading from non-existent path
    config = load_config("/non/existent/path.toml")
    assert config == {}

    # Test loading with None (should use default paths)
    config = load_config(None)
    assert isinstance(config, dict)


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
    # Mock parameters
    mock_ollama_model_param = Option(["--ollama-model"], default="original-model")
    mock_log_level_param = Option(["--log-level"], default="original-log-level")
    mock_quiet_param = Option(["--quiet"], default=False, is_flag=True)
    mock_clipboard_param = Option(["--clipboard"], default=True, is_flag=True)

    # Mock subcommands
    mock_autocorrect_cmd = Command(
        name="autocorrect",
        params=[mock_ollama_model_param, mock_log_level_param, mock_quiet_param],
    )
    mock_transcribe_cmd = Command(
        name="transcribe",
        params=[mock_ollama_model_param, mock_log_level_param, mock_clipboard_param],
    )

    # Mock main command
    mock_main_command = MagicMock()
    mock_main_command.commands = {
        "autocorrect": mock_autocorrect_cmd,
        "transcribe": mock_transcribe_cmd,
    }

    ctx = Context(command=mock_main_command)

    # Test with no subcommand (should set default_map)
    ctx.invoked_subcommand = None
    set_config_defaults(ctx, str(config_file))
    assert ctx.default_map == {"log_level": "INFO", "llm_local_model": "wildcard-model"}

    # Test with autocorrect subcommand
    ctx.invoked_subcommand = "autocorrect"
    ctx.default_map = {}  # Reset default_map
    set_config_defaults(ctx, str(config_file))

    # Check that the defaults on the parameters themselves have been updated
    assert ctx.default_map.get("llm_local_model") == "autocorrect-model"
    assert ctx.default_map.get("log_level") == "INFO"
    assert ctx.default_map.get("quiet") is True

    # Test with transcribe subcommand
    # Reset param defaults before testing the next command
    mock_ollama_model_param.default = "original-model"
    mock_log_level_param.default = "original-log-level"
    ctx.default_map = {}  # Reset default_map

    ctx.invoked_subcommand = "transcribe"
    set_config_defaults(ctx, str(config_file))
    assert ctx.default_map.get("llm_local_model") == "transcribe-model"
    assert ctx.default_map.get("clipboard") is False


@patch("agent_cli.config_loader.CONFIG_PATH")
@patch("agent_cli.config_loader.CONFIG_PATH_2")
def test_default_config_paths(mock_path2: Path, mock_path1: Path, config_file: Path) -> None:
    """Test that default config paths are checked in order."""
    # Neither path exists
    mock_path1.exists.return_value = False  # type: ignore[attr-defined]
    mock_path2.exists.return_value = False  # type: ignore[attr-defined]
    config = load_config(None)
    assert config == {}

    # Only CONFIG_PATH_2 exists
    mock_path1.exists.return_value = False  # type: ignore[attr-defined]
    mock_path2.exists.return_value = True  # type: ignore[attr-defined]
    mock_path2.open.return_value.__enter__.return_value = config_file.open("rb")  # type: ignore[attr-defined]
    config = load_config(None)
    assert config["llm"]["local"]["model"] == "wildcard-model"

    # CONFIG_PATH exists (takes precedence)
    mock_path1.exists.return_value = True  # type: ignore[attr-defined]
    mock_path2.exists.return_value = True  # type: ignore[attr-defined]
    mock_path1.open.return_value.__enter__.return_value = config_file.open("rb")  # type: ignore[attr-defined]
    config = load_config(None)
    assert config["llm"]["local"]["model"] == "wildcard-model"


@patch("agent_cli.config_loader.console")
def test_config_file_error_handling(mock_console: MagicMock, tmp_path: Path) -> None:
    """Test config loading with invalid TOML."""
    invalid_toml = tmp_path / "invalid.toml"
    invalid_toml.write_text("invalid toml content [[[")

    config = load_config(str(invalid_toml))

    assert config == {}
    mock_console.print.assert_called_once()
