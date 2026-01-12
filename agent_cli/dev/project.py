"""Project type detection and setup for the dev module."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class ProjectType:
    """Detected project type with setup commands."""

    name: str
    setup_commands: list[str]
    description: str


def _is_unidep_monorepo(path: Path) -> bool:
    """Check if this is a unidep monorepo with multiple requirements.yaml files.

    A monorepo is detected when there are requirements.yaml files in subdirectories,
    indicating multiple packages managed together. Searches up to 2 levels deep.
    """
    # Check for requirements.yaml or [tool.unidep] in subdirectories (depth 1-2)
    for subdir in path.iterdir():
        if not subdir.is_dir() or subdir.name.startswith("."):
            continue
        # Check immediate children
        if (subdir / "requirements.yaml").exists():
            return True
        pyproject = subdir / "pyproject.toml"
        if pyproject.exists() and "[tool.unidep]" in pyproject.read_text():
            return True
        # Check one level deeper (e.g., packages/pkg1/)
        for nested in subdir.iterdir():
            if not nested.is_dir() or nested.name.startswith("."):
                continue
            if (nested / "requirements.yaml").exists():
                return True
            nested_pyproject = nested / "pyproject.toml"
            if nested_pyproject.exists() and "[tool.unidep]" in nested_pyproject.read_text():
                return True
    return False


def _detect_unidep_project(path: Path) -> ProjectType | None:
    """Detect unidep project and determine the appropriate install command.

    For single projects: unidep install -e .
    For monorepos: unidep install-all -e

    Evidence: https://github.com/basnijholt/unidep README documents these commands.
    """
    has_requirements_yaml = (path / "requirements.yaml").exists()
    has_tool_unidep = False

    if (path / "pyproject.toml").exists():
        pyproject_content = (path / "pyproject.toml").read_text()
        has_tool_unidep = "[tool.unidep]" in pyproject_content

    # Determine if this is a monorepo (multiple requirements.yaml in subdirs)
    is_monorepo = _is_unidep_monorepo(path)

    # Detect monorepo even without root requirements.yaml
    # (subdirs with requirements.yaml is enough)
    if is_monorepo:
        return ProjectType(
            name="python-unidep-monorepo",
            setup_commands=["unidep install-all -e"],
            description="Python monorepo with unidep",
        )

    # Single project requires root requirements.yaml or [tool.unidep]
    if has_requirements_yaml or has_tool_unidep:
        return ProjectType(
            name="python-unidep",
            setup_commands=["unidep install -e ."],
            description="Python project with unidep",
        )

    return None


def detect_project_type(path: Path) -> ProjectType | None:  # noqa: PLR0911
    """Detect the project type based on files present.

    Returns the first matching project type with setup commands.
    """
    # Python with uv (highest priority for Python)
    if (path / "uv.lock").exists() or (
        (path / "pyproject.toml").exists() and "uv" in (path / "pyproject.toml").read_text()
    ):
        return ProjectType(
            name="python-uv",
            setup_commands=["uv sync"],
            description="Python project with uv",
        )

    # Python with unidep (Conda + Pip unified dependency management)
    # Check for requirements.yaml (primary unidep config) or [tool.unidep] in pyproject.toml
    unidep_project = _detect_unidep_project(path)
    if unidep_project is not None:
        return unidep_project

    # Python with Poetry
    if (path / "poetry.lock").exists():
        return ProjectType(
            name="python-poetry",
            setup_commands=["poetry install"],
            description="Python project with Poetry",
        )

    # Python with pip/requirements.txt
    if (path / "requirements.txt").exists():
        return ProjectType(
            name="python-pip",
            setup_commands=["pip install -r requirements.txt"],
            description="Python project with pip",
        )

    # Python with pyproject.toml (generic)
    if (path / "pyproject.toml").exists():
        return ProjectType(
            name="python",
            setup_commands=["pip install -e ."],
            description="Python project",
        )

    # Node.js with pnpm
    if (path / "pnpm-lock.yaml").exists():
        return ProjectType(
            name="node-pnpm",
            setup_commands=["pnpm install"],
            description="Node.js project with pnpm",
        )

    # Node.js with yarn
    if (path / "yarn.lock").exists():
        return ProjectType(
            name="node-yarn",
            setup_commands=["yarn install"],
            description="Node.js project with Yarn",
        )

    # Node.js with npm
    if (path / "package-lock.json").exists() or (path / "package.json").exists():
        return ProjectType(
            name="node-npm",
            setup_commands=["npm install"],
            description="Node.js project with npm",
        )

    # Rust
    if (path / "Cargo.toml").exists():
        return ProjectType(
            name="rust",
            setup_commands=["cargo build"],
            description="Rust project",
        )

    # Go
    if (path / "go.mod").exists():
        return ProjectType(
            name="go",
            setup_commands=["go mod download"],
            description="Go project",
        )

    # Ruby with Bundler
    if (path / "Gemfile.lock").exists() or (path / "Gemfile").exists():
        return ProjectType(
            name="ruby",
            setup_commands=["bundle install"],
            description="Ruby project with Bundler",
        )

    return None


def run_setup(
    path: Path,
    project_type: ProjectType | None = None,
    *,
    capture_output: bool = True,
) -> tuple[bool, str]:
    """Run the setup commands for a project.

    Args:
        path: Path to the project directory
        project_type: Detected project type (auto-detected if None)
        capture_output: Whether to capture output or stream to console

    Returns:
        Tuple of (success, output_or_error)

    """
    if project_type is None:
        project_type = detect_project_type(path)

    if project_type is None:
        return True, "No project type detected, skipping setup"

    outputs: list[str] = []

    for cmd in project_type.setup_commands:
        try:
            result = subprocess.run(  # noqa: S602
                cmd,
                check=False,
                shell=True,
                cwd=path,
                capture_output=capture_output,
                text=True,
            )
            if result.returncode != 0:
                error = result.stderr.strip() if result.stderr else f"Command failed: {cmd}"
                return False, error
            if result.stdout:
                outputs.append(result.stdout.strip())
        except Exception as e:
            return False, str(e)

    return True, "\n".join(outputs) if outputs else f"Setup complete: {project_type.name}"


def copy_env_files(
    source: Path,
    dest: Path,
    patterns: list[str] | None = None,
) -> list[Path]:
    """Copy environment and config files from source to destination.

    Args:
        source: Source directory (main repo)
        dest: Destination directory (worktree)
        patterns: File patterns to copy (default: common env files)

    Returns:
        List of copied file paths

    """
    if patterns is None:
        patterns = [
            ".env",
            ".env.local",
            ".env.example",
            ".envrc",
        ]

    copied: list[Path] = []

    for pattern in patterns:
        # Handle both exact matches and glob patterns
        if "*" in pattern:
            source_files = list(source.glob(pattern))
        else:
            source_file = source / pattern
            source_files = [source_file] if source_file.exists() else []

        for src_file in source_files:
            if src_file.is_file():
                dest_file = dest / src_file.relative_to(source)
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_bytes(src_file.read_bytes())
                copied.append(dest_file)

    return copied


def is_direnv_available() -> bool:
    """Check if direnv is installed and available."""
    return shutil.which("direnv") is not None


def detect_venv_path(path: Path) -> Path | None:
    """Detect the virtual environment path in a project.

    Checks common venv directory names.
    """
    venv_names = [".venv", "venv", ".env", "env"]
    for name in venv_names:
        venv_path = path / name
        # Check for Python venv structure (has bin/activate or Scripts/activate)
        if (venv_path / "bin" / "activate").exists():
            return venv_path
        if (venv_path / "Scripts" / "activate").exists():  # Windows
            return venv_path
    return None


def _get_python_envrc(path: Path, project_name: str) -> str | None:
    """Get .envrc content for Python projects."""
    if project_name == "python-uv":
        venv_path = detect_venv_path(path)
        return f"source {venv_path.name}/bin/activate" if venv_path else "source .venv/bin/activate"
    if project_name == "python-poetry":
        return 'source "$(poetry env info --path)/bin/activate"'
    if project_name in ("python-unidep", "python-unidep-monorepo"):
        # unidep projects typically use conda/micromamba environments
        # Generate activation using shell hooks (micromamba preferred, conda fallback)
        env_name = path.name
        return f"""\
# Activate conda/micromamba environment (tries micromamba first, then conda)
eval "$(micromamba shell hook --shell=bash 2>/dev/null || conda shell.bash hook 2>/dev/null)"
micromamba activate {env_name} 2>/dev/null || conda activate {env_name}"""
    # Generic Python - look for existing venv
    venv_path = detect_venv_path(path)
    return f"source {venv_path.name}/bin/activate" if venv_path else None


def _get_envrc_for_project(path: Path, project_type: ProjectType) -> str | None:
    """Get .envrc content for a specific project type."""
    name = project_type.name

    if name.startswith("python"):
        return _get_python_envrc(path, name)

    if name.startswith("node"):
        has_node_version = (path / ".nvmrc").exists() or (path / ".node-version").exists()
        return "use node" if has_node_version else None

    if name == "go":
        return "layout go"

    if name == "ruby":
        return "layout ruby"

    return None


def _is_nix_available() -> bool:
    """Check if nix is available on the system."""
    return shutil.which("nix") is not None


def _get_nix_envrc(path: Path) -> str | None:
    """Get .envrc content for Nix projects.

    Returns 'use flake' for flake.nix, 'use nix' for shell.nix.
    """
    if not _is_nix_available():
        return None

    # Prefer flake.nix over shell.nix
    if (path / "flake.nix").exists():
        return "use flake"
    if (path / "shell.nix").exists():
        return "use nix"

    return None


def generate_envrc_content(path: Path, project_type: ProjectType | None = None) -> str | None:
    """Generate .envrc content based on project type and environment.

    Args:
        path: Path to the project directory
        project_type: Detected project type (auto-detected if None)

    Returns:
        Content for .envrc file, or None if no direnv config needed

    """
    if project_type is None:
        project_type = detect_project_type(path)

    lines: list[str] = []

    # Check for Nix first (sets up the base environment)
    nix_content = _get_nix_envrc(path)
    if nix_content:
        lines.append(nix_content)

    # Add project-specific content
    if project_type:
        project_content = _get_envrc_for_project(path, project_type)
        if project_content:
            lines.append(project_content)

    # Fallback: check for Python venv without detected project type
    if not lines:
        venv_path = detect_venv_path(path)
        if venv_path:
            lines.append(f"source {venv_path.name}/bin/activate")

    if not lines:
        return None

    return "\n".join(lines) + "\n"


def setup_direnv(
    path: Path,
    project_type: ProjectType | None = None,
    *,
    allow: bool = True,
) -> tuple[bool, str]:
    """Set up direnv for a project by creating .envrc file.

    Args:
        path: Path to the project directory
        project_type: Detected project type (auto-detected if None)
        allow: Whether to run `direnv allow` after creating .envrc

    Returns:
        Tuple of (success, message)

    """
    if not is_direnv_available():
        return False, "direnv is not installed"

    envrc_path = path / ".envrc"

    # Don't overwrite existing .envrc
    if envrc_path.exists():
        return True, ".envrc already exists, skipping"

    content = generate_envrc_content(path, project_type)
    if content is None:
        return True, "No direnv configuration needed for this project"

    # Write .envrc file
    envrc_path.write_text(content)

    # Run direnv allow to trust the file
    if allow:
        result = subprocess.run(
            ["direnv", "allow"],  # noqa: S607
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return True, f"Created .envrc but 'direnv allow' failed: {result.stderr}"

    return True, f"Created .envrc: {content.strip()}"
