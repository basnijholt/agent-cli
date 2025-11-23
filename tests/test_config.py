"""Test the config loading."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from click import Command
from typer import Context
from typer.testing import CliRunner

from agent_cli.cli import app, set_config_defaults
from agent_cli.config import ProviderSelection, load_config, normalize_provider_defaults

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
llm-ollama-model = "default-local-model"
llm-ollama-host = "http://localhost:11434"
llm-openai-model = "default-openai-model"
openai-api-key = "default-key"

[autocorrect]
llm-provider = "openai"
quiet = true
llm-openai-model = "autocorrect-openai-model"
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
    assert config["autocorrect"]["llm_openai_model"] == "autocorrect-openai-model"


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
        "llm_provider": "ollama",
        "llm_ollama_model": "default-local-model",
        "llm_ollama_host": "http://localhost:11434",
        "llm_openai_model": "default-openai-model",
        "openai_api_key": "default-key",
    }
    assert ctx.default_map == expected_defaults

    # Test with autocorrect subcommand (should merge defaults)
    ctx.command.name = "autocorrect"
    ctx.default_map = {}  # Reset
    set_config_defaults(ctx, str(config_file))

    # Check combined defaults: [autocorrect] overrides [defaults]
    expected_merged_defaults = {
        "log_level": "INFO",
        "llm_provider": "openai",  # Overridden by [autocorrect]
        "llm_ollama_model": "default-local-model",
        "llm_ollama_host": "http://localhost:11434",
        "llm_openai_model": "autocorrect-openai-model",  # Overridden by [autocorrect]
        "openai_api_key": "default-key",
        "quiet": True,  # Added by [autocorrect]
    }
    assert ctx.default_map == expected_merged_defaults


def test_provider_alias_normalization(config_file: Path) -> None:
    """Ensure deprecated provider names are normalized."""
    config = load_config(str(config_file))
    normalized_defaults = normalize_provider_defaults(config["defaults"])
    assert normalized_defaults["llm_provider"] == "ollama"

    provider_cfg = ProviderSelection(
        llm_provider="local",
        asr_provider="local",
        tts_provider="wyoming",
    )
    assert provider_cfg.llm_provider == "ollama"
    assert provider_cfg.asr_provider == "wyoming"
    assert provider_cfg.tts_provider == "wyoming"


def test_rag_server_help_includes_config_option(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure rag-server command wires config option (for defaults loading)."""
    monkeypatch.setenv("NO_COLOR", "1")
    result = runner.invoke(app, ["rag-server", "--help"])
    assert result.exit_code == 0
    # Strip ANSI color codes for more reliable testing
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert "--config" in clean_output


def test_server_help_includes_config_option(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure server command wires config option (for defaults loading)."""
    monkeypatch.setenv("NO_COLOR", "1")
    result = runner.invoke(app, ["server", "--help"])
    assert result.exit_code == 0
    # Strip ANSI color codes for more reliable testing
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert "--config" in clean_output
