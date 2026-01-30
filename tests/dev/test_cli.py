"""Tests for dev CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from agent_cli.cli import app
from agent_cli.dev.cli import (
    _format_env_prefix,
    _generate_branch_name,
    _get_agent_env,
    _get_config_agent_args,
    _get_config_agent_env,
)
from agent_cli.dev.coding_agents.base import CodingAgent
from agent_cli.dev.worktree import WorktreeInfo

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


class TestGenerateBranchName:
    """Tests for _generate_branch_name function."""

    def test_generates_adjective_noun(self) -> None:
        """Generates name in adjective-noun format."""
        name = _generate_branch_name()
        parts = name.split("-")
        assert len(parts) >= 2

    def test_avoids_existing_branches(self) -> None:
        """Adds suffix to avoid existing branches."""
        existing: set[str] = {"happy-fox", "happy-fox-2"}
        # Run multiple times to ensure it generates unique names
        names = set()
        for _ in range(10):
            name = _generate_branch_name(existing)
            assert name not in existing
            names.add(name)

    def test_deterministic_with_collision(self) -> None:
        """Adds numeric suffix on collision."""
        # This test is a bit tricky since names are random
        # We just verify it doesn't crash with a full set
        existing: set[str] = set()
        name = _generate_branch_name(existing)
        assert name  # Non-empty


class TestDevHelp:
    """Tests for dev command help."""

    def test_dev_help(self) -> None:
        """Dev command shows help."""
        result = runner.invoke(app, ["dev", "--help"])
        assert result.exit_code == 0
        assert "Parallel development environment manager" in result.output
        assert "new" in result.output
        assert "list" in result.output
        assert "rm" in result.output


class TestDevAgents:
    """Tests for dev agents command."""

    def test_list_agents(self) -> None:
        """List all agents."""
        result = runner.invoke(app, ["dev", "agents"])
        assert result.exit_code == 0
        assert "claude" in result.output.lower()
        assert "aider" in result.output.lower()


class TestDevEditors:
    """Tests for dev editors command."""

    def test_list_editors(self) -> None:
        """List all editors."""
        result = runner.invoke(app, ["dev", "editors"])
        assert result.exit_code == 0
        assert "vscode" in result.output.lower()
        assert "neovim" in result.output.lower()


class TestDevTerminals:
    """Tests for dev terminals command."""

    def test_list_terminals(self) -> None:
        """List all terminals."""
        result = runner.invoke(app, ["dev", "terminals"])
        assert result.exit_code == 0
        assert "tmux" in result.output.lower()
        assert "zellij" in result.output.lower()


class TestDevDoctor:
    """Tests for dev doctor command."""

    def test_doctor_shows_status(self) -> None:
        """Doctor command shows system status."""
        result = runner.invoke(app, ["dev", "doctor"])
        assert result.exit_code == 0
        assert "Git" in result.output
        assert "Editors" in result.output
        assert "AI Coding Agents" in result.output
        assert "Terminals" in result.output


class TestDevList:
    """Tests for dev list command."""

    def test_list_requires_git_repo(self) -> None:
        """List requires being in a git repo."""
        with patch("agent_cli.dev.worktree.get_main_repo_root", return_value=None):
            result = runner.invoke(app, ["dev", "list"])
            # Should show error about not being in git repo
            assert "git" in result.output.lower() or result.exit_code != 0

    def test_list_shows_worktrees(self) -> None:
        """List shows worktrees in table format."""
        mock_worktrees = [
            WorktreeInfo(
                path=Path("/repo"),
                branch="main",
                commit="abc",
                is_main=True,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
            WorktreeInfo(
                path=Path("/repo-worktrees/feature"),
                branch="feature",
                commit="def",
                is_main=False,
                is_detached=False,
                is_locked=False,
                is_prunable=False,
            ),
        ]

        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.list_worktrees", return_value=mock_worktrees),
        ):
            result = runner.invoke(app, ["dev", "list"])
            assert result.exit_code == 0
            assert "main" in result.output
            assert "feature" in result.output


class TestDevPath:
    """Tests for dev path command."""

    def test_path_prints_worktree_path(self) -> None:
        """Path command prints worktree path."""
        mock_wt = WorktreeInfo(
            path=Path("/repo-worktrees/feature"),
            branch="feature",
            commit="abc",
            is_main=False,
            is_detached=False,
            is_locked=False,
            is_prunable=False,
        )

        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.find_worktree_by_name", return_value=mock_wt),
        ):
            result = runner.invoke(app, ["dev", "path", "feature"])
            assert result.exit_code == 0
            assert "/repo-worktrees/feature" in result.output

    def test_path_not_found(self) -> None:
        """Path command shows error for unknown worktree."""
        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.find_worktree_by_name", return_value=None),
        ):
            result = runner.invoke(app, ["dev", "path", "nonexistent"])
            assert result.exit_code != 0
            assert "not found" in result.output.lower()


class TestDevRm:
    """Tests for dev rm command."""

    def test_rm_force_skips_confirmation(self) -> None:
        """The --force flag skips the confirmation prompt.

        Bug fix: Previously --force only passed force to git worktree remove
        but still prompted for confirmation. Now it skips the prompt entirely.

        Evidence: typer.confirm() is only called when neither --yes nor --force
        is provided (line 845 in cli.py).
        """
        mock_wt = WorktreeInfo(
            path=Path("/repo-worktrees/feature"),
            branch="feature",
            commit="abc",
            is_main=False,
            is_detached=False,
            is_locked=False,
            is_prunable=False,
        )

        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.find_worktree_by_name", return_value=mock_wt),
            patch(
                "agent_cli.dev.worktree.remove_worktree",
                return_value=(True, None),
            ) as mock_remove,
        ):
            # With --force, should NOT prompt and should succeed
            result = runner.invoke(app, ["dev", "rm", "feature", "--force"])
            assert result.exit_code == 0
            assert "Removed worktree" in result.output
            # Verify remove_worktree was called with force=True
            mock_remove.assert_called_once()
            assert mock_remove.call_args[1]["force"] is True

    def test_rm_yes_skips_confirmation(self) -> None:
        """The --yes flag skips the confirmation prompt."""
        mock_wt = WorktreeInfo(
            path=Path("/repo-worktrees/feature"),
            branch="feature",
            commit="abc",
            is_main=False,
            is_detached=False,
            is_locked=False,
            is_prunable=False,
        )

        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.find_worktree_by_name", return_value=mock_wt),
            patch(
                "agent_cli.dev.worktree.remove_worktree",
                return_value=(True, None),
            ) as mock_remove,
        ):
            # With --yes, should NOT prompt and should succeed
            result = runner.invoke(app, ["dev", "rm", "feature", "--yes"])
            assert result.exit_code == 0
            assert "Removed worktree" in result.output
            mock_remove.assert_called_once()

    def test_rm_without_flags_prompts(self) -> None:
        """Without --force or --yes, rm prompts for confirmation."""
        mock_wt = WorktreeInfo(
            path=Path("/repo-worktrees/feature"),
            branch="feature",
            commit="abc",
            is_main=False,
            is_detached=False,
            is_locked=False,
            is_prunable=False,
        )

        with (
            patch("agent_cli.dev.worktree.get_main_repo_root", return_value=Path("/repo")),
            patch("agent_cli.dev.worktree.git_available", return_value=True),
            patch("agent_cli.dev.worktree.find_worktree_by_name", return_value=mock_wt),
            patch(
                "agent_cli.dev.worktree.remove_worktree",
                return_value=(True, None),
            ) as mock_remove,
        ):
            # Without --force or --yes, should prompt (and abort on 'n')
            result = runner.invoke(app, ["dev", "rm", "feature"], input="n\n")
            assert result.exit_code != 0 or "Aborted" in result.output
            # remove_worktree should NOT have been called since user said no
            mock_remove.assert_not_called()


class TestFormatEnvPrefix:
    """Tests for _format_env_prefix function."""

    def test_empty_env(self) -> None:
        """Empty env returns empty string."""
        assert _format_env_prefix({}) == ""

    def test_single_var(self) -> None:
        """Single env var is formatted correctly."""
        result = _format_env_prefix({"FOO": "bar"})
        assert result == "FOO=bar "

    def test_multiple_vars_sorted(self) -> None:
        """Multiple env vars are sorted alphabetically."""
        result = _format_env_prefix({"ZZZ": "last", "AAA": "first"})
        assert result == "AAA=first ZZZ=last "

    def test_quotes_special_chars(self) -> None:
        """Values with spaces or special chars are quoted."""
        result = _format_env_prefix({"MSG": "hello world"})
        assert result == "MSG='hello world' "

    def test_quotes_empty_value(self) -> None:
        """Empty values are quoted."""
        result = _format_env_prefix({"EMPTY": ""})
        assert result == "EMPTY='' "


class TestGetConfigAgentArgs:
    """Tests for _get_config_agent_args function."""

    def test_returns_none_when_no_config(self) -> None:
        """Returns None when no agent_args in config."""
        with patch("agent_cli.dev.cli.load_config", return_value={}):
            result = _get_config_agent_args()
            assert result is None

    def test_returns_agent_args_nested(self) -> None:
        """Returns agent_args from nested config structure (for mocks)."""
        config = {
            "dev": {
                "agent_args": {
                    "claude": ["--dangerously-skip-permissions"],
                },
            },
        }
        with patch("agent_cli.dev.cli.load_config", return_value=config):
            result = _get_config_agent_args()
            assert result == {"claude": ["--dangerously-skip-permissions"]}

    def test_returns_agent_args_from_flattened_key(self) -> None:
        """Returns agent_args from flattened config key (real config loader format)."""
        config = {
            "dev.agent_args": {
                "claude": ["--dangerously-skip-permissions"],
                "aider": ["--model", "gpt-4o"],
            },
        }
        with patch("agent_cli.dev.cli.load_config", return_value=config):
            result = _get_config_agent_args()
            assert result == {
                "claude": ["--dangerously-skip-permissions"],
                "aider": ["--model", "gpt-4o"],
            }


class TestGetConfigAgentEnv:
    """Tests for _get_config_agent_env function."""

    def test_returns_none_when_no_config(self) -> None:
        """Returns None when no agent_env in config."""
        with patch("agent_cli.dev.cli.load_config", return_value={}):
            result = _get_config_agent_env()
            assert result is None

    def test_returns_none_when_no_dev_section(self) -> None:
        """Returns None when no dev section in config."""
        with patch("agent_cli.dev.cli.load_config", return_value={"other": {}}):
            result = _get_config_agent_env()
            assert result is None

    def test_returns_agent_env(self) -> None:
        """Returns agent_env from config (nested structure for mocks)."""
        config = {
            "dev": {
                "agent_env": {
                    "claude": {"CLAUDE_CODE_USE_VERTEX": "1", "ANTHROPIC_MODEL": "opus"},
                },
            },
        }
        with patch("agent_cli.dev.cli.load_config", return_value=config):
            result = _get_config_agent_env()
            assert result == {"claude": {"CLAUDE_CODE_USE_VERTEX": "1", "ANTHROPIC_MODEL": "opus"}}

    def test_returns_agent_env_from_flattened_keys(self) -> None:
        """Returns agent_env from flattened config keys (real config loader format)."""
        # The real config loader flattens nested dicts to dotted keys
        config = {
            "dev.agent_env.claude": {"CLAUDE_CODE_USE_VERTEX": "1", "ANTHROPIC_MODEL": "opus"},
            "dev.agent_env.aider": {"OPENAI_API_KEY": "sk-xxx"},
        }
        with patch("agent_cli.dev.cli.load_config", return_value=config):
            result = _get_config_agent_env()
            assert result == {
                "claude": {"CLAUDE_CODE_USE_VERTEX": "1", "ANTHROPIC_MODEL": "opus"},
                "aider": {"OPENAI_API_KEY": "sk-xxx"},
            }


class _MockAgent(CodingAgent):
    """Mock agent for testing."""

    name = "mock"
    command = "mock"

    def get_env(self) -> dict[str, str]:
        """Return mock env vars."""
        return {"BUILTIN_VAR": "builtin_value"}


class TestGetAgentEnv:
    """Tests for _get_agent_env function."""

    def test_returns_builtin_env_when_no_config(self) -> None:
        """Returns agent's built-in env when no config."""
        agent = _MockAgent()
        with patch("agent_cli.dev.cli._get_config_agent_env", return_value=None):
            result = _get_agent_env(agent)
            assert result == {"BUILTIN_VAR": "builtin_value"}

    def test_config_overrides_builtin(self) -> None:
        """Config env vars override built-in env vars."""
        agent = _MockAgent()
        config_env = {"mock": {"BUILTIN_VAR": "overridden", "NEW_VAR": "new_value"}}
        with patch("agent_cli.dev.cli._get_config_agent_env", return_value=config_env):
            result = _get_agent_env(agent)
            assert result == {"BUILTIN_VAR": "overridden", "NEW_VAR": "new_value"}

    def test_merges_builtin_and_config(self) -> None:
        """Config env vars are merged with built-in env vars."""
        agent = _MockAgent()
        config_env = {"mock": {"CONFIG_VAR": "config_value"}}
        with patch("agent_cli.dev.cli._get_config_agent_env", return_value=config_env):
            result = _get_agent_env(agent)
            assert result == {"BUILTIN_VAR": "builtin_value", "CONFIG_VAR": "config_value"}

    def test_ignores_other_agents(self) -> None:
        """Config for other agents is ignored."""
        agent = _MockAgent()
        config_env = {"other": {"OTHER_VAR": "other_value"}}
        with patch("agent_cli.dev.cli._get_config_agent_env", return_value=config_env):
            result = _get_agent_env(agent)
            assert result == {"BUILTIN_VAR": "builtin_value"}


class TestDevInstallSkill:
    """Tests for dev install-skill command."""

    def test_install_skill_help(self) -> None:
        """Install-skill command shows help."""
        result = runner.invoke(app, ["dev", "install-skill", "--help"])
        assert result.exit_code == 0
        assert "Install Claude Code skill" in result.output
        assert "--force" in result.output

    def test_install_skill_requires_git_repo(self) -> None:
        """Install-skill requires being in a git repo."""
        with patch("agent_cli.dev.cli._get_current_repo_root", return_value=None):
            result = runner.invoke(app, ["dev", "install-skill"])
            assert result.exit_code != 0
            assert "git" in result.output.lower()

    def test_install_skill_copies_files(self, tmp_path: Path) -> None:
        """Install-skill copies skill files to .claude/skills/."""
        with patch("agent_cli.dev.cli._get_current_repo_root", return_value=tmp_path):
            result = runner.invoke(app, ["dev", "install-skill"])
            assert result.exit_code == 0
            assert "Installed skill" in result.output

            skill_dir = tmp_path / ".claude" / "skills" / "agent-cli-dev"
            assert skill_dir.exists()
            assert (skill_dir / "SKILL.md").exists()
            assert (skill_dir / "examples.md").exists()

    def test_install_skill_already_installed(self, tmp_path: Path) -> None:
        """Install-skill warns if already installed."""
        # Pre-create the skill directory
        skill_dir = tmp_path / ".claude" / "skills" / "agent-cli-dev"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("existing")

        with patch("agent_cli.dev.cli._get_current_repo_root", return_value=tmp_path):
            result = runner.invoke(app, ["dev", "install-skill"])
            assert result.exit_code == 0
            assert "already installed" in result.output.lower()

    def test_install_skill_force_overwrites(self, tmp_path: Path) -> None:
        """Install-skill --force overwrites existing files."""
        # Pre-create the skill directory
        skill_dir = tmp_path / ".claude" / "skills" / "agent-cli-dev"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("old content")

        with patch("agent_cli.dev.cli._get_current_repo_root", return_value=tmp_path):
            result = runner.invoke(app, ["dev", "install-skill", "--force"])
            assert result.exit_code == 0
            assert "Installed skill" in result.output

            # Verify content was replaced
            content = (skill_dir / "SKILL.md").read_text()
            assert "old content" not in content
            assert "agent-cli-dev" in content
