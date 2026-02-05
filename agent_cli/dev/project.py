"""Project type detection and setup for the dev module."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@dataclass
class ProjectType:
    """Detected project type with setup commands."""

    name: str
    setup_commands: list[str]
    description: str


def get_conda_env_name(path: Path) -> str:
    """Get conda environment name, prefixed with repo name for worktrees.

    For worktrees in `{repo}-worktrees/{branch}`, returns `{repo}-{branch}`.
    For main repos or non-worktree directories, returns just the directory name.

    This prevents conda env name collisions when working on multiple repos
    with similarly named branches (e.g., both repos having a 'cool-bear' branch).

    Evidence: Worktree directories follow the pattern established in worktree.py
    line 239: `repo_root.parent / f"{repo_root.name}-worktrees"`
    """
    parent_name = path.parent.name
    if parent_name.endswith("-worktrees"):
        # Extract repo name by removing '-worktrees' suffix
        repo_name = parent_name[: -len("-worktrees")]
        return f"{repo_name}-{path.name}"
    return path.name


def _is_unidep_monorepo(path: Path) -> bool:
    """Check if this is a unidep monorepo with multiple requirements.yaml files.

    A monorepo is detected when there are requirements.yaml files in subdirectories,
    indicating multiple packages managed together. Searches up to 2 levels deep.
    Excludes common test/example directories to avoid false positives.
    """
    # Directories to exclude from monorepo detection (test fixtures, examples, etc.)
    excluded_dirs = {"test", "tests", "example", "examples", "docs", "doc", "scripts"}

    # Check for requirements.yaml or [tool.unidep] in subdirectories (depth 1-2)
    for subdir in path.iterdir():
        if not subdir.is_dir() or subdir.name.startswith("."):
            continue
        if subdir.name.lower() in excluded_dirs:
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


def _unidep_cmd(subcommand: str) -> str | None:
    """Generate unidep command, checking availability.

    Returns the command to run, or None if neither unidep nor uvx is available.
    Prefers unidep if installed, falls back to uvx.
    """
    if shutil.which("unidep"):
        return f"unidep {subcommand}"
    if shutil.which("uvx"):
        return f"uvx unidep {subcommand}"
    return None


def _detect_unidep_project(path: Path) -> ProjectType | None:
    """Detect unidep project and determine the appropriate install command.

    For single projects: unidep install -e . -n {env_name}
    For monorepos: unidep install-all -e -n {env_name}

    If conda-lock.yml exists, adds -f conda-lock.yml to use the locked dependencies.

    Falls back to `uvx unidep` if unidep is not installed globally.
    The {env_name} placeholder is replaced with path.name at runtime by run_setup().

    Evidence: https://github.com/basnijholt/unidep README documents these commands.
    """
    has_requirements_yaml = (path / "requirements.yaml").exists()
    has_tool_unidep = False

    if (path / "pyproject.toml").exists():
        pyproject_content = (path / "pyproject.toml").read_text()
        has_tool_unidep = "[tool.unidep]" in pyproject_content

    # Check for conda-lock.yml to use locked dependencies
    lock_flag = " -f conda-lock.yml" if (path / "conda-lock.yml").exists() else ""

    # Determine if this is a monorepo (multiple requirements.yaml in subdirs)
    is_monorepo = _is_unidep_monorepo(path)

    # Detect monorepo even without root requirements.yaml
    # (subdirs with requirements.yaml is enough)
    if is_monorepo:
        cmd = _unidep_cmd(f"install-all -e{lock_flag} -n {{env_name}}")
        if cmd is None:
            return None  # Neither unidep nor uvx available
        return ProjectType(
            name="python-unidep-monorepo",
            # -n creates a named conda environment matching the worktree directory
            setup_commands=[cmd],
            description="Python monorepo with unidep",
        )

    # Single project requires root requirements.yaml or [tool.unidep]
    if has_requirements_yaml or has_tool_unidep:
        cmd = _unidep_cmd(f"install -e .{lock_flag} -n {{env_name}}")
        if cmd is None:
            return None  # Neither unidep nor uvx available
        return ProjectType(
            name="python-unidep",
            # -n creates a named conda environment matching the worktree directory
            setup_commands=[cmd],
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
            setup_commands=["uv sync --all-extras"],
            description="Python project with uv",
        )

    # Pixi (cross-platform package manager from prefix.dev)
    # Evidence: https://pixi.sh/latest/ - pixi.toml is the config file, pixi.lock is the lockfile
    if (path / "pixi.toml").exists() or (path / "pixi.lock").exists():
        return ProjectType(
            name="pixi",
            setup_commands=["pixi install"],
            description="Project with pixi",
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
    on_log: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Run the setup commands for a project.

    Args:
        path: Path to the project directory
        project_type: Detected project type (auto-detected if None)
        capture_output: Whether to capture output or stream to console
        on_log: Optional callback for logging status messages

    Returns:
        Tuple of (success, output_or_error)

    """
    if project_type is None:
        project_type = detect_project_type(path)

    if project_type is None:
        return True, "No project type detected, skipping setup"

    outputs: list[str] = []

    for cmd_template in project_type.setup_commands:
        # Substitute {env_name} placeholder with conda env name (used by unidep)
        cmd = cmd_template.replace("{env_name}", get_conda_env_name(path))

        if on_log:
            on_log(f"Running: {cmd}")

        try:
            # Clear virtual environment variables to avoid warnings from uv/pip
            # when running from within an activated environment
            env = os.environ.copy()
            env.pop("VIRTUAL_ENV", None)
            env.pop("CONDA_PREFIX", None)
            env.pop("CONDA_DEFAULT_ENV", None)

            result = subprocess.run(  # noqa: S602
                cmd,
                check=False,
                shell=True,
                cwd=path,
                capture_output=capture_output,
                text=True,
                env=env,
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
        # unidep projects use conda/micromamba environments
        # Inline the activation logic (inspired by layout_micromamba pattern)
        # Uses ${SHELL##*/} to detect shell at runtime (zsh, bash, etc.)
        # Redirect stderr to suppress "complete: command not found" from shell hooks
        # (completion setup commands aren't available in direnv's subshell)
        env_name = get_conda_env_name(path)
        return f"""\
# Activate micromamba/conda environment: {env_name}
if command -v micromamba &> /dev/null; then
    eval "$(micromamba shell hook --shell=${{SHELL##*/}})" 2>/dev/null
    micromamba activate {env_name}
elif command -v conda &> /dev/null; then
    eval "$(conda shell.${{SHELL##*/}} hook)" 2>/dev/null
    conda activate {env_name}
fi"""
    # Generic Python - look for existing venv
    venv_path = detect_venv_path(path)
    return f"source {venv_path.name}/bin/activate" if venv_path else None


def _get_envrc_for_project(path: Path, project_type: ProjectType) -> str | None:
    """Get .envrc content for a specific project type."""
    name = project_type.name

    if name == "pixi":
        # Evidence: https://pixi.sh/latest/features/environment/#direnv
        # watch_file ensures direnv reloads when dependencies change
        return 'watch_file pixi.lock\neval "$(pixi shell-hook)"'

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


def _run_direnv_allow(
    path: Path,
    on_log: Callable[[str], None] | None = None,
    capture_output: bool = True,
) -> str | None:
    """Run `direnv allow` in the given path.

    Returns:
        None on success, error message on failure.

    """
    if on_log:
        on_log("Running: direnv allow")
    result = subprocess.run(
        ["direnv", "allow"],  # noqa: S607
        cwd=path,
        capture_output=capture_output,
        text=True,
        check=False,
    )
    return result.stderr if result.returncode != 0 and result.stderr else None


def setup_direnv(
    path: Path,
    project_type: ProjectType | None = None,
    *,
    allow: bool = True,
    on_log: Callable[[str], None] | None = None,
    capture_output: bool = True,
) -> tuple[bool, str]:
    """Set up direnv for a project by creating .envrc file.

    Args:
        path: Path to the project directory
        project_type: Detected project type (auto-detected if None)
        allow: Whether to run `direnv allow` after creating .envrc
        on_log: Optional callback for logging status messages
        capture_output: Whether to capture command output (False to stream)

    Returns:
        Tuple of (success, message)

    """
    if not is_direnv_available():
        return False, "direnv is not installed"

    envrc_path = path / ".envrc"

    # If .envrc already exists, just run direnv allow on it
    if envrc_path.exists():
        if not allow:
            return True, "direnv: .envrc already exists (skipped direnv allow)"
        error = _run_direnv_allow(path, on_log, capture_output=capture_output)
        msg = (
            "direnv: allowed existing .envrc"
            if not error
            else f"direnv: .envrc exists but 'direnv allow' failed: {error}"
        )
        return True, msg

    content = generate_envrc_content(path, project_type)
    if content is None:
        return True, "direnv: no configuration needed for this project type"

    # Write .envrc file
    if on_log:
        on_log("Creating .envrc file for direnv")
    envrc_path.write_text(content)

    # Run direnv allow to trust the file
    if allow:
        error = _run_direnv_allow(path, on_log, capture_output=capture_output)
        if error:
            return True, f"direnv: created .envrc but 'direnv allow' failed: {error}"

    return True, f"direnv: created .envrc ({content.strip()})"
