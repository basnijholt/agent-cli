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
    _get_install_hint,
    _maybe_reexec_after_install,
    _resolve_extras_for_install,
    _should_skip_extra_check_for_process_control,
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

    def test__get_install_hint_with_pipe_syntax(self) -> None:
        """Pipe syntax shows all alternatives in the hint."""
        hint = _get_install_hint("piper|kokoro")
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


class TestResolveExtrasForInstall:
    """Test the _resolve_extras_for_install function."""

    def test_passes_through_simple_extras(self) -> None:
        """Simple extras without | should pass through unchanged."""
        result = _resolve_extras_for_install(("audio", "llm"))
        assert result == ["audio", "llm"]

    def test_resolves_alternatives_to_first_when_none_installed(self) -> None:
        """Alternatives like 'piper|kokoro' should pick the first option when none installed."""
        with patch("agent_cli.core.deps._check_extra_installed", return_value=False):
            result = _resolve_extras_for_install(("audio", "piper|kokoro"))
            assert result == ["audio", "piper"]

    def test_resolves_alternatives_to_installed(self) -> None:
        """Alternatives should pick the installed one if present."""

        def check_installed(extra: str) -> bool:
            return extra == "kokoro"

        with patch("agent_cli.core.deps._check_extra_installed", side_effect=check_installed):
            result = _resolve_extras_for_install(("piper|kokoro",))
            assert result == ["kokoro"]


class TestCheckAndInstallExtras:
    """Test the _check_and_install_extras function."""

    def test_returns_empty_when_all_installed(self) -> None:
        """Should return empty list when all extras are already installed."""
        with patch("agent_cli.core.deps._check_extra_installed", return_value=True):
            result = _check_and_install_extras(("audio", "llm"))
            assert result == []

    def test_returns_missing_when_auto_install_disabled(self) -> None:
        """Should return missing list without installing when disabled."""
        with (
            patch("agent_cli.core.deps._check_extra_installed", return_value=False),
            patch("agent_cli.core.deps._get_auto_install_setting", return_value=False),
            patch("agent_cli.core.deps.print_error_message") as mock_error,
        ):
            result = _check_and_install_extras(("fake-extra",))
            assert result == ["fake-extra"]
            mock_error.assert_called_once()

    def test_returns_missing_when_install_fails(self) -> None:
        """Should return missing list when auto-install fails."""
        with (
            patch("agent_cli.core.deps._check_extra_installed", return_value=False),
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
                "agent_cli.core.deps._check_extra_installed",
                side_effect=lambda _: next(check_results),
            ),
            patch("agent_cli.core.deps._get_auto_install_setting", return_value=True),
            patch("agent_cli.core.deps._try_auto_install", return_value=True),
            patch("agent_cli.core.deps._maybe_reexec_after_install"),  # Prevent actual re-exec
        ):
            result = _check_and_install_extras(("fake-extra",))
            assert result == []

    def test_returns_still_missing_after_partial_install(self) -> None:
        """Should return still-missing extras after install completes."""
        # First check: missing, install succeeds, second check: still missing
        with (
            patch("agent_cli.core.deps._check_extra_installed", return_value=False),
            patch("agent_cli.core.deps._get_auto_install_setting", return_value=True),
            patch("agent_cli.core.deps._try_auto_install", return_value=True),
            patch("agent_cli.core.deps._maybe_reexec_after_install"),  # Prevent actual re-exec
            patch("agent_cli.core.deps.print_error_message") as mock_error,
        ):
            result = _check_and_install_extras(("fake-extra",))
            assert result == ["fake-extra"]
            mock_error.assert_called_once()
            assert "not visible" in mock_error.call_args[0][0]


class TestReexecBehavior:
    """Test re-exec behavior after auto-install."""

    def test_reexec_uses_original_argv0(self) -> None:
        """Re-exec should preserve the command path that launched agent-cli."""
        with (
            patch("agent_cli.core.deps._maybe_exec_with_marker") as mock_reexec,
            patch("sys.argv", ["/custom/bin/agent-cli", "transcribe", "--toggle"]),
        ):
            _maybe_reexec_after_install()

        mock_reexec.assert_called_once_with(
            ["/custom/bin/agent-cli", "transcribe", "--toggle"],
            "Re-running with installed extras...",
        )

    def test_reexec_falls_back_to_python_module_when_argv0_missing(self) -> None:
        """Re-exec should still work if argv[0] is unavailable."""
        with (
            patch("agent_cli.core.deps._maybe_exec_with_marker") as mock_reexec,
            patch("sys.argv", ["", "transcribe", "--toggle"]),
            patch("sys.executable", "/usr/bin/python3"),
        ):
            _maybe_reexec_after_install()

        mock_reexec.assert_called_once_with(
            ["/usr/bin/python3", "-m", "agent_cli.cli", "transcribe", "--toggle"],
            "Re-running with installed extras...",
        )


class TestProcessControlBypass:
    """Test process-control bypasses for dependency checks."""

    def test_skip_for_stop_and_status(self) -> None:
        """Stop/status commands should not trigger extra checks."""
        assert _should_skip_extra_check_for_process_control({"stop": True}, "transcribe") is True
        assert _should_skip_extra_check_for_process_control({"status": True}, "transcribe") is True

    def test_skip_for_toggle_when_process_running(self) -> None:
        """Toggle should bypass extra checks when it is acting as stop."""
        with patch("agent_cli.core.process.is_process_running", return_value=True):
            assert (
                _should_skip_extra_check_for_process_control({"toggle": True}, "transcribe") is True
            )

    def test_no_skip_for_toggle_when_process_not_running(self) -> None:
        """Toggle start still needs dependency checks."""
        with patch("agent_cli.core.process.is_process_running", return_value=False):
            assert (
                _should_skip_extra_check_for_process_control({"toggle": True}, "transcribe")
                is False
            )

    def test_decorator_skips_extra_checks_for_toggle_stop(self) -> None:
        """Decorated commands should stop an existing process without installing extras."""
        with (
            patch("agent_cli.core.process.is_process_running", return_value=True),
            patch("agent_cli.core.deps._check_and_install_extras") as mock_check,
        ):

            @requires_extras("audio", process_name="transcribe")
            def my_command(**kwargs: object) -> str:
                assert kwargs["toggle"] is True
                return "stopped"

            assert my_command(toggle=True) == "stopped"

        mock_check.assert_not_called()


class TestDecoratorIntegration:
    """Test the requires_extras decorator end-to-end behavior."""

    def test_calls_function_when_extras_installed(self) -> None:
        """Decorated function should run when extras are installed."""
        with patch("agent_cli.core.deps._check_extra_installed", return_value=True):

            @requires_extras("audio")
            def my_command() -> str:
                return "success"

            assert my_command() == "success"

    def test_exits_when_extras_missing_and_auto_install_disabled(self) -> None:
        """Should exit when extras missing and auto-install is disabled."""
        with (
            patch("agent_cli.core.deps._check_extra_installed", return_value=False),
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
                "agent_cli.core.deps._check_extra_installed",
                side_effect=lambda _: next(check_results),
            ),
            patch("agent_cli.core.deps._get_auto_install_setting", return_value=True),
            patch("agent_cli.core.deps._try_auto_install", return_value=True),
            patch("agent_cli.core.deps._maybe_reexec_after_install"),  # Prevent actual re-exec
        ):

            @requires_extras("fake-extra")
            def my_command() -> str:
                return "success"

            assert my_command() == "success"

    def test_exits_when_auto_install_fails(self) -> None:
        """Should exit when auto-install fails."""
        with (
            patch("agent_cli.core.deps._check_extra_installed", return_value=False),
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
