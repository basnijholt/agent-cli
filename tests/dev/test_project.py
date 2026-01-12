"""Tests for project type detection and setup."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from agent_cli.dev.project import (
    copy_env_files,
    detect_project_type,
    detect_venv_path,
    generate_envrc_content,
)


class TestDetectProjectType:
    """Tests for detect_project_type function."""

    def test_python_uv_with_lock(self, tmp_path: Path) -> None:
        """Detect Python project with uv.lock."""
        (tmp_path / "uv.lock").touch()
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python-uv"
        assert "uv sync" in project.setup_commands

    def test_python_uv_in_pyproject(self, tmp_path: Path) -> None:
        """Detect Python project with uv in pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[tool.uv]\ndev-dependencies = []")
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python-uv"

    def test_python_poetry(self, tmp_path: Path) -> None:
        """Detect Python project with Poetry."""
        (tmp_path / "poetry.lock").touch()
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python-poetry"
        assert "poetry install" in project.setup_commands

    def test_python_pip(self, tmp_path: Path) -> None:
        """Detect Python project with requirements.txt."""
        (tmp_path / "requirements.txt").write_text("requests>=2.0")
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python-pip"

    def test_python_generic(self, tmp_path: Path) -> None:
        """Detect generic Python project with pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"')
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python"

    def test_node_pnpm(self, tmp_path: Path) -> None:
        """Detect Node.js project with pnpm."""
        (tmp_path / "pnpm-lock.yaml").touch()
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "node-pnpm"
        assert "pnpm install" in project.setup_commands

    def test_node_yarn(self, tmp_path: Path) -> None:
        """Detect Node.js project with Yarn."""
        (tmp_path / "yarn.lock").touch()
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "node-yarn"

    def test_node_npm(self, tmp_path: Path) -> None:
        """Detect Node.js project with npm."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "node-npm"

    def test_rust(self, tmp_path: Path) -> None:
        """Detect Rust project."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "rust"
        assert "cargo build" in project.setup_commands

    def test_go(self, tmp_path: Path) -> None:
        """Detect Go project."""
        (tmp_path / "go.mod").write_text("module example.com/test")
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "go"

    def test_ruby(self, tmp_path: Path) -> None:
        """Detect Ruby project."""
        (tmp_path / "Gemfile").write_text('source "https://rubygems.org"')
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "ruby"

    def test_no_project_detected(self, tmp_path: Path) -> None:
        """Return None for unknown project type."""
        project = detect_project_type(tmp_path)
        assert project is None

    def test_priority_uv_over_pyproject(self, tmp_path: Path) -> None:
        """uv.lock takes priority over bare pyproject.toml."""
        (tmp_path / "uv.lock").touch()
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"')
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python-uv"

    def test_python_unidep_with_requirements_yaml(self, tmp_path: Path) -> None:
        """Detect Python project with unidep via requirements.yaml.

        Evidence: https://github.com/basnijholt/unidep - requirements.yaml is
        the primary configuration file for unidep projects.
        """
        (tmp_path / "requirements.yaml").write_text("dependencies:\n  - numpy")
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python-unidep"
        # -n {env_name} creates a named conda environment (placeholder replaced at runtime)
        assert "unidep install -e . -n {env_name}" in project.setup_commands

    def test_python_unidep_with_tool_unidep_in_pyproject(self, tmp_path: Path) -> None:
        """Detect Python project with unidep via [tool.unidep] in pyproject.toml.

        Evidence: https://github.com/basnijholt/unidep - [tool.unidep] section
        in pyproject.toml is an alternative to requirements.yaml.
        """
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\n\n[tool.unidep]\ndependencies = ["numpy"]',
        )
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python-unidep"
        # -n {env_name} creates a named conda environment (placeholder replaced at runtime)
        assert "unidep install -e . -n {env_name}" in project.setup_commands

    def test_python_unidep_monorepo(self, tmp_path: Path) -> None:
        """Detect Python monorepo with unidep (multiple requirements.yaml).

        Evidence: https://github.com/basnijholt/unidep - unidep install-all
        is used for monorepos with multiple packages.
        """
        # Root requirements.yaml
        (tmp_path / "requirements.yaml").write_text("dependencies:\n  - numpy")
        # Subpackage with its own requirements.yaml
        subpkg = tmp_path / "packages" / "pkg1"
        subpkg.mkdir(parents=True)
        (subpkg / "requirements.yaml").write_text("dependencies:\n  - pandas")

        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python-unidep-monorepo"
        # -n {env_name} creates a named conda environment (placeholder replaced at runtime)
        assert "unidep install-all -e -n {env_name}" in project.setup_commands

    def test_python_unidep_monorepo_with_tool_unidep(self, tmp_path: Path) -> None:
        """Detect monorepo when subdirs have [tool.unidep] in pyproject.toml."""
        (tmp_path / "requirements.yaml").write_text("dependencies:\n  - numpy")
        subpkg = tmp_path / "packages" / "pkg1"
        subpkg.mkdir(parents=True)
        (subpkg / "pyproject.toml").write_text('[tool.unidep]\ndependencies = ["pandas"]')

        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python-unidep-monorepo"

    def test_priority_uv_over_unidep(self, tmp_path: Path) -> None:
        """Uv takes priority over unidep when both are present."""
        (tmp_path / "uv.lock").touch()
        (tmp_path / "requirements.yaml").write_text("dependencies:\n  - numpy")
        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python-uv"

    def test_python_unidep_monorepo_without_root_requirements(self, tmp_path: Path) -> None:
        """Detect monorepo when subdirs have requirements.yaml but root doesn't.

        Evidence: https://github.com/basnijholt/unidep/tree/main/tests/simple_monorepo
        shows a monorepo structure with only subdirs having requirements.yaml.
        """
        # No root requirements.yaml, only subdirs
        subpkg1 = tmp_path / "project1"
        subpkg2 = tmp_path / "project2"
        subpkg1.mkdir()
        subpkg2.mkdir()
        (subpkg1 / "requirements.yaml").write_text("dependencies:\n  - numpy")
        (subpkg2 / "requirements.yaml").write_text("dependencies:\n  - pandas")

        project = detect_project_type(tmp_path)
        assert project is not None
        assert project.name == "python-unidep-monorepo"
        # -n {env_name} creates a named conda environment (placeholder replaced at runtime)
        assert "unidep install-all -e -n {env_name}" in project.setup_commands

    def test_python_unidep_excludes_test_example_dirs(self, tmp_path: Path) -> None:
        """Exclude test/example directories from monorepo detection.

        Evidence: Directories like tests/, example/, docs/ often contain
        requirements.yaml files as test fixtures, not actual dependencies.
        """
        # Only requirements.yaml in excluded directories - should NOT be monorepo
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myproject"')
        for excluded in ["tests", "example", "docs"]:
            subdir = tmp_path / excluded / "fixture"
            subdir.mkdir(parents=True)
            (subdir / "requirements.yaml").write_text("dependencies:\n  - numpy")

        project = detect_project_type(tmp_path)
        # Should detect as generic python, not unidep monorepo
        assert project is not None
        assert project.name == "python"
        assert project.name != "python-unidep-monorepo"


class TestDetectVenvPath:
    """Tests for detect_venv_path function."""

    def test_detect_venv(self, tmp_path: Path) -> None:
        """Detect .venv directory."""
        venv = tmp_path / ".venv" / "bin"
        venv.mkdir(parents=True)
        (venv / "activate").touch()
        result = detect_venv_path(tmp_path)
        assert result == tmp_path / ".venv"

    def test_detect_venv_named_venv(self, tmp_path: Path) -> None:
        """Detect venv directory."""
        venv = tmp_path / "venv" / "bin"
        venv.mkdir(parents=True)
        (venv / "activate").touch()
        result = detect_venv_path(tmp_path)
        assert result == tmp_path / "venv"

    def test_no_venv(self, tmp_path: Path) -> None:
        """Return None when no venv found."""
        result = detect_venv_path(tmp_path)
        assert result is None

    def test_directory_without_activate_not_detected(self, tmp_path: Path) -> None:
        """Directory named .venv without activate script is not a venv."""
        (tmp_path / ".venv").mkdir()
        result = detect_venv_path(tmp_path)
        assert result is None


class TestGenerateEnvrcContent:
    """Tests for generate_envrc_content function."""

    def test_python_uv_with_venv(self, tmp_path: Path) -> None:
        """Generate envrc for Python uv project with venv."""
        (tmp_path / "uv.lock").touch()
        venv = tmp_path / ".venv" / "bin"
        venv.mkdir(parents=True)
        (venv / "activate").touch()
        content = generate_envrc_content(tmp_path)
        assert content is not None
        assert "source .venv/bin/activate" in content

    def test_python_poetry(self, tmp_path: Path) -> None:
        """Generate envrc for Poetry project."""
        (tmp_path / "poetry.lock").touch()
        content = generate_envrc_content(tmp_path)
        assert content is not None
        assert "poetry env info" in content

    def test_node_with_nvmrc(self, tmp_path: Path) -> None:
        """Generate envrc for Node project with .nvmrc."""
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / ".nvmrc").write_text("18")
        content = generate_envrc_content(tmp_path)
        assert content is not None
        assert "use node" in content

    def test_go_project(self, tmp_path: Path) -> None:
        """Generate envrc for Go project."""
        (tmp_path / "go.mod").write_text("module test")
        content = generate_envrc_content(tmp_path)
        assert content is not None
        assert "layout go" in content

    def test_no_envrc_needed(self, tmp_path: Path) -> None:
        """Return None when no envrc needed."""
        content = generate_envrc_content(tmp_path)
        assert content is None

    def test_fallback_to_venv_detection(self, tmp_path: Path) -> None:
        """Fallback to venv detection without project type."""
        venv = tmp_path / ".venv" / "bin"
        venv.mkdir(parents=True)
        (venv / "activate").touch()
        content = generate_envrc_content(tmp_path)
        assert content is not None
        assert "source .venv/bin/activate" in content

    def test_python_unidep_generates_conda_activation(self, tmp_path: Path) -> None:
        """Unidep projects generate micromamba/conda activation in envrc.

        Evidence: unidep projects use conda/micromamba environments.
        The generated .envrc uses shell hooks with runtime shell detection.
        Stderr is redirected to suppress "complete: command not found" errors
        from shell completion setup that isn't available in direnv's subshell.
        """
        (tmp_path / "requirements.yaml").write_text("dependencies:\n  - numpy")
        content = generate_envrc_content(tmp_path)
        assert content is not None
        assert "micromamba shell hook" in content
        assert "micromamba activate" in content
        assert "conda" in content  # fallback
        # Uses directory name as env name
        assert tmp_path.name in content
        # Stderr redirected to suppress completion errors in direnv subshell
        assert "2>/dev/null" in content

    def test_python_unidep_monorepo_generates_conda_activation(self, tmp_path: Path) -> None:
        """Unidep monorepo generates micromamba/conda activation in envrc."""
        (tmp_path / "requirements.yaml").write_text("dependencies:\n  - numpy")
        subpkg = tmp_path / "pkg1"
        subpkg.mkdir()
        (subpkg / "requirements.yaml").write_text("dependencies:\n  - pandas")

        content = generate_envrc_content(tmp_path)
        assert content is not None
        assert "micromamba activate" in content


class TestCopyEnvFiles:
    """Tests for copy_env_files function."""

    def test_copy_env_file(self, tmp_path: Path) -> None:
        """Copy .env file."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        (source / ".env").write_text("SECRET=value")

        copied = copy_env_files(source, dest)
        assert len(copied) == 1
        assert (dest / ".env").exists()
        assert (dest / ".env").read_text() == "SECRET=value"

    def test_copy_multiple_env_files(self, tmp_path: Path) -> None:
        """Copy multiple env files."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        (source / ".env").write_text("A=1")
        (source / ".env.local").write_text("B=2")

        copied = copy_env_files(source, dest)
        assert len(copied) == 2

    def test_skip_missing_files(self, tmp_path: Path) -> None:
        """Skip files that don't exist."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()

        copied = copy_env_files(source, dest)
        assert len(copied) == 0

    def test_custom_patterns(self, tmp_path: Path) -> None:
        """Use custom file patterns."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        (source / "custom.conf").write_text("config")

        copied = copy_env_files(source, dest, patterns=["custom.conf"])
        assert len(copied) == 1
        assert (dest / "custom.conf").exists()
