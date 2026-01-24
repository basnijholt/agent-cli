"""Tests for @requires_extras decorator functionality."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

from agent_cli.core.deps import (
    EXTRAS,
    _get_auto_install_setting,
    check_extra_installed,
    get_install_hint,
    requires_extras,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestRequiresExtrasDecorator:
    """Test the requires_extras decorator functionality."""

    def test_decorator_stores_extras_on_function(self) -> None:
        """The decorator should store required extras on the function."""

        @requires_extras("audio", "llm")
        def sample_command() -> str:
            return "success"

        assert hasattr(sample_command, "_required_extras")
        assert sample_command._required_extras == ("audio", "llm")

    def test_check_extra_installed_unknown_extra(self) -> None:
        """Unknown extras should return True (assume OK)."""
        assert check_extra_installed("nonexistent-extra") is True

    def test_check_extra_installed_with_pipe_syntax(self) -> None:
        """Pipe syntax means any of the extras is sufficient."""
        # At least one should be true (unknown extras return True)
        assert check_extra_installed("nonexistent|also-nonexistent") is True
        # piper|kokoro - at least one may be installed in dev env
        result = check_extra_installed("piper|kokoro")
        assert isinstance(result, bool)  # Just verify it doesn't error

    def test_get_install_hint_with_pipe_syntax(self) -> None:
        """Pipe syntax shows all alternatives in the hint."""
        hint = get_install_hint("piper|kokoro")
        assert "requires one of:" in hint
        assert "'piper'" in hint
        assert "'kokoro'" in hint
        # Brackets are escaped for rich markup (\\[)
        assert "agent-cli\\[piper]" in hint
        assert "agent-cli\\[kokoro]" in hint


class TestExtrasMetadata:
    """Test the _extras.json metadata is properly structured."""

    def test_extras_dict_structure(self) -> None:
        """EXTRAS dict should have proper structure."""
        assert isinstance(EXTRAS, dict)
        for name, value in EXTRAS.items():
            assert isinstance(name, str)
            assert isinstance(value, tuple)
            assert len(value) == 2
            desc, packages = value
            assert isinstance(desc, str)
            assert isinstance(packages, list)
            assert all(isinstance(pkg, str) for pkg in packages)

    def test_essential_extras_present(self) -> None:
        """Essential extras should be defined."""
        essential = ["audio", "llm", "rag", "memory", "vad"]
        for extra in essential:
            assert extra in EXTRAS, f"Missing essential extra: {extra}"


class TestAutoInstallSetting:
    """Test the auto-install extras configuration."""

    def test_default_is_enabled(self) -> None:
        """Auto-install should be enabled by default."""
        env = dict(os.environ)
        env.pop("AGENT_CLI_NO_AUTO_INSTALL", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch("agent_cli.core.deps._CONFIG_PATHS", []),
        ):
            assert _get_auto_install_setting() is True

    def test_env_var_disables(self) -> None:
        """AGENT_CLI_NO_AUTO_INSTALL=1 should disable auto-install."""
        with patch.dict(os.environ, {"AGENT_CLI_NO_AUTO_INSTALL": "1"}):
            assert _get_auto_install_setting() is False

    def test_env_var_true_disables(self) -> None:
        """AGENT_CLI_NO_AUTO_INSTALL=true should disable auto-install."""
        with patch.dict(os.environ, {"AGENT_CLI_NO_AUTO_INSTALL": "true"}):
            assert _get_auto_install_setting() is False

    def test_env_var_yes_disables(self) -> None:
        """AGENT_CLI_NO_AUTO_INSTALL=yes should disable auto-install."""
        with patch.dict(os.environ, {"AGENT_CLI_NO_AUTO_INSTALL": "yes"}):
            assert _get_auto_install_setting() is False

    def test_config_file_disables(self, tmp_path: Path) -> None:
        """Config file with auto_install_extras = false should disable."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("auto_install_extras = false\n")

        env = dict(os.environ)
        env.pop("AGENT_CLI_NO_AUTO_INSTALL", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch("agent_cli.core.deps._CONFIG_PATHS", [config_file]),
        ):
            assert _get_auto_install_setting() is False

    def test_config_file_enables(self, tmp_path: Path) -> None:
        """Config file with auto_install_extras = true should enable."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("auto_install_extras = true\n")

        env = dict(os.environ)
        env.pop("AGENT_CLI_NO_AUTO_INSTALL", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch("agent_cli.core.deps._CONFIG_PATHS", [config_file]),
        ):
            assert _get_auto_install_setting() is True

    def test_env_var_takes_precedence(self, tmp_path: Path) -> None:
        """Environment variable should take precedence over config file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("auto_install_extras = true\n")

        with (
            patch.dict(os.environ, {"AGENT_CLI_NO_AUTO_INSTALL": "1"}),
            patch("agent_cli.core.deps._CONFIG_PATHS", [config_file]),
        ):
            assert _get_auto_install_setting() is False
