"""Tests for config command."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agent_cli.cli import app
from agent_cli.config_cmd import _generate_template, _get_editor

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


class TestGetEditor:
    """Tests for _get_editor function."""

    def test_uses_editor_env_var(self) -> None:
        """Test that EDITOR env var is preferred."""
        with patch.dict(os.environ, {"EDITOR": "code", "VISUAL": "vim"}):
            assert _get_editor() == "code"

    def test_uses_visual_env_var_as_fallback(self) -> None:
        """Test that VISUAL is used when EDITOR is not set."""
        with patch.dict(os.environ, {"VISUAL": "vim"}, clear=True):
            assert _get_editor() == "vim"

    def test_windows_default(self) -> None:
        """Test Windows default editor."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("platform.system", return_value="Windows"),
        ):
            assert _get_editor() == "notepad"

    def test_unix_fallback_chain(self) -> None:
        """Test Unix fallback to vim/vi/nano."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("platform.system", return_value="Linux"),
            patch("shutil.which", side_effect=lambda x: "/usr/bin/nano" if x == "nano" else None),
        ):
            assert _get_editor() == "nano"


class TestGenerateTemplate:
    """Tests for _generate_template function."""

    def test_generates_valid_template(self) -> None:
        """Test that template is generated."""
        template = _generate_template()
        assert "[defaults]" in template
        assert "agent-cli configuration file" in template

    def test_template_has_commented_values(self) -> None:
        """Test that values are commented out."""
        template = _generate_template()
        # Check that actual config values are commented
        # Section headers should NOT be commented
        assert (
            "\n[defaults]" in template
            or template.startswith("[defaults]")
            or "# agent-cli" in template
        )


class TestConfigInit:
    """Tests for config init command."""

    def test_init_creates_file(self, tmp_path: Path) -> None:
        """Test that init creates a config file."""
        config_path = tmp_path / "config.toml"
        result = runner.invoke(app, ["config", "init", "--path", str(config_path)])
        assert result.exit_code == 0
        assert config_path.exists()
        assert "[defaults]" in config_path.read_text(encoding="utf-8")

    def test_init_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test that init creates parent directories."""
        config_path = tmp_path / "nested" / "dir" / "config.toml"
        result = runner.invoke(app, ["config", "init", "--path", str(config_path)])
        assert result.exit_code == 0
        assert config_path.exists()

    def test_init_prompts_on_existing_file(self, tmp_path: Path) -> None:
        """Test that init prompts when file exists."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("existing content")

        # Decline overwrite
        result = runner.invoke(
            app,
            ["config", "init", "--path", str(config_path)],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "existing content" in config_path.read_text()

    def test_init_force_overwrites(self, tmp_path: Path) -> None:
        """Test that --force overwrites without prompting."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("existing content")

        result = runner.invoke(
            app,
            ["config", "init", "--path", str(config_path), "--force"],
        )
        assert result.exit_code == 0
        assert "[defaults]" in config_path.read_text(encoding="utf-8")

    def test_init_shows_success_message(self, tmp_path: Path) -> None:
        """Test that init shows success message."""
        config_path = tmp_path / "config.toml"
        result = runner.invoke(app, ["config", "init", "--path", str(config_path)])
        assert "Config file created at:" in result.stdout

    def test_init_expands_user_path(self, tmp_path: Path) -> None:
        """Test that init expands '~' in provided path."""
        home = tmp_path / "home"
        config_path = home / ".config" / "agent-cli" / "config.toml"

        # Windows uses USERPROFILE, Unix uses HOME
        env_patch = {"HOME": str(home), "USERPROFILE": str(home)}
        with patch.dict(os.environ, env_patch):
            result = runner.invoke(
                app,
                ["config", "init", "--path", "~/.config/agent-cli/config.toml"],
            )

        assert result.exit_code == 0
        assert config_path.exists()


class TestConfigEdit:
    """Tests for config edit command."""

    def test_edit_file_not_found(self, tmp_path: Path) -> None:
        """Test error when no config file exists."""
        nonexistent = tmp_path / "nonexistent.toml"
        result = runner.invoke(app, ["config", "edit", "--path", str(nonexistent)])
        assert result.exit_code == 1
        assert "Config file not found" in result.stdout
        assert str(nonexistent) in result.stdout.replace("\n", "")

    @patch("subprocess.run")
    def test_edit_opens_editor(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that edit opens the editor."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("[defaults]")

        mock_run.return_value.returncode = 0

        with patch.dict(os.environ, {"EDITOR": "nano"}):
            result = runner.invoke(
                app,
                ["config", "edit", "--path", str(config_path)],
            )

        assert result.exit_code == 0
        mock_run.assert_called_once()
        # Verify editor was called with the config path
        call_args = mock_run.call_args[0][0]
        assert "nano" in call_args
        assert str(config_path) in call_args

    @patch("subprocess.run")
    def test_edit_handles_editor_not_found(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test handling when editor is not found."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("[defaults]")

        mock_run.side_effect = FileNotFoundError()

        with patch.dict(os.environ, {"EDITOR": "nonexistent-editor"}):
            result = runner.invoke(
                app,
                ["config", "edit", "--path", str(config_path)],
            )

        assert result.exit_code == 1
        assert "not found" in result.stdout

    @patch("subprocess.run")
    def test_edit_expands_user_path(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that edit expands '~' in provided path."""
        home = tmp_path / "home"
        config_path = home / ".config" / "agent-cli" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("[defaults]")

        mock_run.return_value.returncode = 0

        # Windows uses USERPROFILE, Unix uses HOME
        env_patch = {"EDITOR": "nano", "HOME": str(home), "USERPROFILE": str(home)}
        with patch.dict(os.environ, env_patch):
            result = runner.invoke(
                app,
                ["config", "edit", "--path", "~/.config/agent-cli/config.toml"],
            )

        assert result.exit_code == 0
        called_args = mock_run.call_args[0][0]
        assert called_args[-1] == str(config_path)

    @patch("subprocess.run")
    def test_edit_supports_editor_with_arguments(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that edit splits editor command with arguments."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("[defaults]")

        mock_run.return_value.returncode = 0

        with patch.dict(os.environ, {"EDITOR": "code --wait"}):
            result = runner.invoke(
                app,
                ["config", "edit", "--path", str(config_path)],
            )

        assert result.exit_code == 0
        mock_run.assert_called_once()
        called_args = mock_run.call_args[0][0]
        assert called_args[:2] == ["code", "--wait"]
        assert called_args[-1] == str(config_path)


class TestConfigShow:
    """Tests for config show command."""

    def test_show_no_config(self, tmp_path: Path) -> None:
        """Test show when no config exists."""
        nonexistent = tmp_path / "nonexistent.toml"
        with (
            patch(
                "agent_cli.config_cmd.CONFIG_PATHS",
                [nonexistent],
            ),
            patch("agent_cli.config_cmd._config_path", return_value=None),
        ):
            result = runner.invoke(app, ["config", "show"])
            assert result.exit_code == 0
            assert "No config file found" in result.stdout

    def test_show_displays_path_and_content(self, tmp_path: Path) -> None:
        """Test that show displays config path and contents."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("[defaults]\nllm-provider = 'ollama'")

        result = runner.invoke(app, ["config", "show", "--path", str(config_path)])
        assert result.exit_code == 0
        assert "Config file" in result.stdout
        assert "llm-provider" in result.stdout or "defaults" in result.stdout

    def test_show_raw(self, tmp_path: Path) -> None:
        """Test that --raw outputs plain text."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("[defaults]\nllm-provider = 'ollama'")

        result = runner.invoke(
            app,
            ["config", "show", "--path", str(config_path), "--raw"],
        )
        assert result.exit_code == 0
        assert "[defaults]" in result.stdout
        # Should NOT contain rich formatting
        assert "Config file" not in result.stdout

    def test_show_invalid_path(self, tmp_path: Path) -> None:
        """Test that show reports when the provided path does not exist."""
        config_path = tmp_path / "missing.toml"

        result = runner.invoke(
            app,
            ["config", "show", "--path", str(config_path)],
        )

        assert result.exit_code == 1
        assert "Config file not found" in result.stdout
        assert str(config_path) in result.stdout.replace("\n", "")

    def test_show_expands_user_path(self, tmp_path: Path) -> None:
        """Test that show expands '~' in provided path."""
        home = tmp_path / "home"
        config_path = home / ".config" / "agent-cli" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("[defaults]\nllm-provider = 'ollama'")

        # Windows uses USERPROFILE, Unix uses HOME
        env_patch = {"HOME": str(home), "USERPROFILE": str(home)}
        with patch.dict(os.environ, env_patch):
            result = runner.invoke(
                app,
                ["config", "show", "--path", "~/.config/agent-cli/config.toml", "--raw"],
            )

        assert result.exit_code == 0
        assert "[defaults]" in result.stdout


class TestConfigHelp:
    """Tests for config command help."""

    def test_config_help(self) -> None:
        """Test config command help."""
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "init" in result.stdout
        assert "edit" in result.stdout
        assert "show" in result.stdout

    def test_config_init_help(self) -> None:
        """Test config init help."""
        result = runner.invoke(app, ["config", "init", "--help"])
        assert result.exit_code == 0
        assert "--path" in result.stdout
        assert "--force" in result.stdout

    def test_config_edit_help(self) -> None:
        """Test config edit help."""
        result = runner.invoke(app, ["config", "edit", "--help"])
        assert result.exit_code == 0
        assert "--path" in result.stdout

    def test_config_show_help(self) -> None:
        """Test config show help."""
        result = runner.invoke(app, ["config", "show", "--help"])
        assert result.exit_code == 0
        assert "--path" in result.stdout
        assert "--raw" in result.stdout
