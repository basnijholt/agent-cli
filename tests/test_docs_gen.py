"""Tests for the docs_gen module."""

from __future__ import annotations

from agent_cli.docs_gen import (
    _format_default,
    _get_command_options,
    _list_commands,
    _options_by_panel,
    _options_table,
    all_options_for_docs,
    commands_table,
    config_example,
    env_vars_table,
    provider_matrix,
)

# --- Tests for _format_default ---


def test_format_default_none_returns_dash() -> None:
    """Test that None returns a dash."""
    assert _format_default(None) == "-"


def test_format_default_bool_true() -> None:
    """Test that True returns lowercase 'true'."""
    assert _format_default(True) == "true"


def test_format_default_bool_false() -> None:
    """Test that False returns lowercase 'false'."""
    assert _format_default(False) == "false"


def test_format_default_empty_string() -> None:
    """Test that empty string returns quoted empty string."""
    assert _format_default("") == '""'


def test_format_default_string_value() -> None:
    """Test that string values are returned as-is."""
    assert _format_default("hello") == "hello"


def test_format_default_integer_value() -> None:
    """Test that integer values are converted to string."""
    assert _format_default(42) == "42"


# --- Tests for _get_command_options ---


def test_get_command_options_transcribe() -> None:
    """Test that transcribe command options are extracted."""
    options = _get_command_options("transcribe")
    assert len(options) > 0
    for opt in options:
        assert "name" in opt
        assert "type" in opt
        assert "default" in opt
        assert "help" in opt
        assert "panel" in opt


def test_get_command_options_nonexistent() -> None:
    """Test that nonexistent command returns empty list."""
    options = _get_command_options("nonexistent")
    assert options == []


def test_get_command_options_subcommand() -> None:
    """Test that subcommand options are extracted."""
    options = _get_command_options("memory.proxy")
    assert len(options) > 0


# --- Tests for _options_table ---


def test_options_table_generates_markdown() -> None:
    """Test that options_table generates valid markdown table."""
    table = _options_table("transcribe")
    assert "|" in table
    assert "Option" in table
    assert "Description" in table


def test_options_table_filter_by_panel() -> None:
    """Test that panel filtering works."""
    table = _options_table("transcribe", panel="LLM Configuration")
    assert "--llm" in table
    assert "--asr-wyoming-ip" not in table


def test_options_table_nonexistent_panel() -> None:
    """Test that nonexistent panel returns appropriate message."""
    table = _options_table("transcribe", panel="Nonexistent Panel")
    assert "No options found" in table


def test_options_table_include_type_false() -> None:
    """Test that include_type=False excludes Type column."""
    table = _options_table("transcribe", include_type=False)
    lines = table.split("\n")
    header = lines[0]
    assert "Option" in header
    assert "Default" in header
    assert "Description" in header


# --- Tests for _options_by_panel ---


def test_options_by_panel_groups() -> None:
    """Test that options are grouped by panel with headers."""
    result = _options_by_panel("transcribe")
    assert "### " in result or "## " in result


def test_options_by_panel_heading_level() -> None:
    """Test that heading level parameter works."""
    result = _options_by_panel("transcribe", heading_level=2)
    assert "## " in result


def test_options_by_panel_nonexistent_command() -> None:
    """Test that nonexistent command returns appropriate message."""
    result = _options_by_panel("nonexistent")
    assert "No options found" in result


# --- Tests for _list_commands ---


def test_list_commands_returns_list() -> None:
    """Test that list_commands returns a list."""
    commands = _list_commands()
    assert isinstance(commands, list)
    assert len(commands) > 0


def test_list_commands_includes_known() -> None:
    """Test that known commands are in the list."""
    commands = _list_commands()
    assert "transcribe" in commands
    assert "speak" in commands


def test_list_commands_includes_subcommands() -> None:
    """Test that subcommands are included."""
    commands = _list_commands()
    assert any("memory" in cmd for cmd in commands)


def test_list_commands_sorted() -> None:
    """Test that commands are sorted alphabetically."""
    commands = _list_commands()
    assert commands == sorted(commands)


# --- Tests for all_options_for_docs ---


def test_all_options_for_docs_complete() -> None:
    """Test that all_options_for_docs generates complete documentation."""
    result = all_options_for_docs("transcribe")
    assert len(result) > 100
    assert "###" in result
    assert "|" in result


def test_all_options_for_docs_includes_panels() -> None:
    """Test that expected panels are included."""
    result = all_options_for_docs("transcribe")
    assert "LLM Configuration" in result
    assert "Audio Input" in result
    assert "General Options" in result


def test_all_options_for_docs_nonexistent() -> None:
    """Test that nonexistent command returns appropriate message."""
    result = all_options_for_docs("nonexistent")
    assert "No options found" in result


# --- Tests for env_vars_table ---


def test_env_vars_table_generates() -> None:
    """Test that env_vars_table generates valid table."""
    table = env_vars_table()
    assert "|" in table
    assert "Variable" in table
    assert "Description" in table


def test_env_vars_table_includes_known() -> None:
    """Test that known env vars are included."""
    table = env_vars_table()
    assert "OPENAI_API_KEY" in table
    assert "GEMINI_API_KEY" in table


# --- Tests for provider_matrix ---


def test_provider_matrix_generates() -> None:
    """Test that provider_matrix generates valid table."""
    table = provider_matrix()
    assert "|" in table
    assert "Capability" in table


def test_provider_matrix_includes_providers() -> None:
    """Test that known providers are included."""
    table = provider_matrix()
    assert "ollama" in table
    assert "openai" in table
    assert "wyoming" in table


# --- Tests for commands_table ---


def test_commands_table_generates() -> None:
    """Test that commands_table generates valid table."""
    table = commands_table()
    assert "|" in table
    assert "Command" in table
    assert "Purpose" in table


def test_commands_table_includes_known() -> None:
    """Test that known commands are included."""
    table = commands_table()
    assert "transcribe" in table
    assert "speak" in table


def test_commands_table_filter_by_category() -> None:
    """Test that category filtering works."""
    table = commands_table(category="voice")
    assert "transcribe" in table
    assert "speak" in table
    assert "install-services" not in table


def test_commands_table_nonexistent_category() -> None:
    """Test that nonexistent category returns appropriate message."""
    table = commands_table(category="nonexistent")
    assert "No commands found" in table


def test_commands_table_generates_links() -> None:
    """Test that commands_table generates markdown links."""
    table = commands_table()
    assert ".md)" in table


# --- Tests for config_example ---


def test_config_example_defaults() -> None:
    """Test that config_example generates defaults section."""
    config = config_example()
    assert "[defaults]" in config
    assert "llm_provider" in config


def test_config_example_command() -> None:
    """Test that config_example generates command section."""
    config = config_example("transcribe")
    assert "[transcribe]" in config


def test_config_example_nonexistent() -> None:
    """Test that nonexistent command returns appropriate message."""
    config = config_example("nonexistent")
    assert "No configurable options" in config


def test_config_example_subcommand_section() -> None:
    """Test that subcommand dots are replaced with dashes in section name."""
    config = config_example("memory.proxy")
    assert "[memory-proxy]" in config
