"""Project type detection and setup for the space module."""

from __future__ import annotations

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
