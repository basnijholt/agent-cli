"""Tests for @requires_extras decorator functionality."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
import typer

from agent_cli.core.deps import (
    EXTRAS,
    _check_and_install_extras,
    _get_auto_install_setting,
    _try_auto_install,
    get_install_hint,
    requires_extras,
)


class TestRequiresExtrasDecorator:
    """Test the requires_extras decorator functionality."""

    def test_decorator_stores_extras_on_function(self) -> None:
        """The decorator should store required extras on the function."""

        @requires_extras("audio", "llm")
        def sample_command() -> str:
            return "success"

        assert hasattr(sample_command, "_required_extras")
        assert sample_command._required_extras == ("audio", "llm")

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
            patch("agent_cli.core.deps.load_config", return_value={}),
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

    def test_config_file_disables(self) -> None:
        """Config [settings] section with auto_install_extras = false should disable."""
        env = dict(os.environ)
        env.pop("AGENT_CLI_NO_AUTO_INSTALL", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "agent_cli.core.deps.load_config",
                return_value={"settings": {"auto_install_extras": False}},
            ),
        ):
            assert _get_auto_install_setting() is False

    def test_config_file_enables(self) -> None:
        """Config [settings] section with auto_install_extras = true should enable."""
        env = dict(os.environ)
        env.pop("AGENT_CLI_NO_AUTO_INSTALL", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "agent_cli.core.deps.load_config",
                return_value={"settings": {"auto_install_extras": True}},
            ),
        ):
            assert _get_auto_install_setting() is True

    def test_env_var_takes_precedence(self) -> None:
        """Environment variable should take precedence over config file."""
        with (
            patch.dict(os.environ, {"AGENT_CLI_NO_AUTO_INSTALL": "1"}),
            patch(
                "agent_cli.core.deps.load_config",
                return_value={"settings": {"auto_install_extras": True}},
            ),
        ):
            assert _get_auto_install_setting() is False


class TestTryAutoInstall:
    """Test the _try_auto_install function."""

    def test_flattens_alternatives(self) -> None:
        """Alternatives like 'piper|kokoro' should pick the first option."""
        with patch(
            "agent_cli.install.extras.install_extras_programmatic",
            return_value=True,
        ) as mock_install:
            result = _try_auto_install(["audio", "piper|kokoro"])
            assert result is True
            mock_install.assert_called_once_with(["audio", "piper"], quiet=True)

    def test_returns_install_result(self) -> None:
        """Should return the result from install_extras_programmatic."""
        with patch(
            "agent_cli.install.extras.install_extras_programmatic",
            return_value=False,
        ):
            assert _try_auto_install(["audio"]) is False

        with patch(
            "agent_cli.install.extras.install_extras_programmatic",
            return_value=True,
        ):
            assert _try_auto_install(["audio"]) is True


class TestCheckAndInstallExtras:
    """Test the _check_and_install_extras function."""

    def test_returns_empty_when_all_installed(self) -> None:
        """Should return empty list when all extras are already installed."""
        with patch("agent_cli.core.deps.check_extra_installed", return_value=True):
            result = _check_and_install_extras(("audio", "llm"))
            assert result == []

    def test_returns_missing_when_auto_install_disabled(self) -> None:
        """Should return missing list without installing when disabled."""
        with (
            patch("agent_cli.core.deps.check_extra_installed", return_value=False),
            patch("agent_cli.core.deps._get_auto_install_setting", return_value=False),
            patch("agent_cli.core.deps.print_error_message") as mock_error,
        ):
            result = _check_and_install_extras(("fake-extra",))
            assert result == ["fake-extra"]
            mock_error.assert_called_once()

    def test_returns_missing_when_install_fails(self) -> None:
        """Should return missing list when auto-install fails."""
        with (
            patch("agent_cli.core.deps.check_extra_installed", return_value=False),
            patch("agent_cli.core.deps._get_auto_install_setting", return_value=True),
            patch("agent_cli.core.deps._try_auto_install", return_value=False),
            patch("agent_cli.core.deps.print_error_message") as mock_error,
        ):
            result = _check_and_install_extras(("fake-extra",))
            assert result == ["fake-extra"]
            mock_error.assert_called_once()
            assert "Auto-install failed" in mock_error.call_args[0][0]

    def test_returns_empty_when_install_succeeds(self) -> None:
        """Should return empty list when auto-install succeeds."""
        check_results = iter([False, True])  # First call: missing, second: installed
        with (
            patch(
                "agent_cli.core.deps.check_extra_installed",
                side_effect=lambda _: next(check_results),
            ),
            patch("agent_cli.core.deps._get_auto_install_setting", return_value=True),
            patch("agent_cli.core.deps._try_auto_install", return_value=True),
        ):
            result = _check_and_install_extras(("fake-extra",))
            assert result == []

    def test_returns_still_missing_after_partial_install(self) -> None:
        """Should return still-missing extras after install completes."""
        # First check: missing, install succeeds, second check: still missing
        with (
            patch("agent_cli.core.deps.check_extra_installed", return_value=False),
            patch("agent_cli.core.deps._get_auto_install_setting", return_value=True),
            patch("agent_cli.core.deps._try_auto_install", return_value=True),
            patch("agent_cli.core.deps.print_error_message") as mock_error,
        ):
            result = _check_and_install_extras(("fake-extra",))
            assert result == ["fake-extra"]
            mock_error.assert_called_once()
            assert "still missing" in mock_error.call_args[0][0]


class TestDecoratorIntegration:
    """Test the requires_extras decorator end-to-end behavior."""

    def test_calls_function_when_extras_installed(self) -> None:
        """Decorated function should run when extras are installed."""
        with patch("agent_cli.core.deps.check_extra_installed", return_value=True):

            @requires_extras("audio")
            def my_command() -> str:
                return "success"

            assert my_command() == "success"

    def test_exits_when_extras_missing_and_auto_install_disabled(self) -> None:
        """Should exit when extras missing and auto-install is disabled."""
        with (
            patch("agent_cli.core.deps.check_extra_installed", return_value=False),
            patch("agent_cli.core.deps._get_auto_install_setting", return_value=False),
            patch("agent_cli.core.deps.print_error_message"),
        ):

            @requires_extras("fake-extra")
            def my_command() -> str:
                return "success"

            with pytest.raises(typer.Exit) as exc_info:
                my_command()
            assert exc_info.value.exit_code == 1

    def test_auto_installs_and_runs_on_success(self) -> None:
        """Should auto-install, then run the function on success."""
        check_results = iter([False, True])  # Missing first, then installed
        with (
            patch(
                "agent_cli.core.deps.check_extra_installed",
                side_effect=lambda _: next(check_results),
            ),
            patch("agent_cli.core.deps._get_auto_install_setting", return_value=True),
            patch("agent_cli.core.deps._try_auto_install", return_value=True),
        ):

            @requires_extras("fake-extra")
            def my_command() -> str:
                return "success"

            assert my_command() == "success"

    def test_exits_when_auto_install_fails(self) -> None:
        """Should exit when auto-install fails."""
        with (
            patch("agent_cli.core.deps.check_extra_installed", return_value=False),
            patch("agent_cli.core.deps._get_auto_install_setting", return_value=True),
            patch("agent_cli.core.deps._try_auto_install", return_value=False),
            patch("agent_cli.core.deps.print_error_message"),
        ):

            @requires_extras("fake-extra")
            def my_command() -> str:
                return "success"

            with pytest.raises(typer.Exit) as exc_info:
                my_command()
            assert exc_info.value.exit_code == 1
