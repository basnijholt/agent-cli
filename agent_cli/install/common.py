"""Common utilities for installation commands."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from agent_cli.core.utils import print_error_message, print_with_style

if TYPE_CHECKING:
    from subprocess import CompletedProcess


def _script_directory() -> Path:
    """Get the directory containing all scripts."""
    # First check if we're running from source (development)
    source_scripts = Path(__file__).parent.parent.parent / "scripts"
    if source_scripts.exists():
        return source_scripts
    # Check for scripts bundled with the package
    package_scripts = Path(__file__).parent.parent / "scripts"
    if package_scripts.exists():
        return package_scripts
    msg = "Should never happen: no scripts directory found, please report an issue."
    raise RuntimeError(msg)


def get_script_path(script_name: str) -> Path:
    """Get the path to a script in the scripts directory."""
    script_dir = _script_directory()
    return script_dir / script_name


def _run_script(script_path: Path) -> CompletedProcess[bytes]:
    """Run a shell script, streaming its output directly to the terminal."""
    if not script_path.exists():
        msg = f"Script not found: {script_path}"
        raise FileNotFoundError(msg)

    # Run the script through the shell, which handles execution permissions
    # This avoids modifying file permissions in the package directory
    return subprocess.run(
        ["bash", str(script_path)],  # noqa: S607
        check=True,
        cwd=script_path.parent,
    )


def get_platform_script(macos_script: str, linux_script: str) -> str:
    """Get the appropriate script name based on the platform."""
    system = platform.system().lower()

    if system == "darwin":
        return macos_script
    if system == "linux":
        return linux_script
    print_error_message(f"Unsupported operating system: {system}")
    raise typer.Exit(1) from None


def execute_installation_script(
    script_name: str,
    operation_name: str,
    success_message: str,
    next_steps: list[str] | None = None,
) -> None:
    """Execute an installation script with standard error handling."""
    script_path = get_script_path(script_name)
    print_with_style(f"🚀 Running {script_name} to {operation_name.lower()}...", "green")

    try:
        _run_script(script_path)
        print_with_style(f"✅ {success_message}", "green")
        if next_steps:
            print_with_style("\nNext steps:", "yellow")
            for i, step in enumerate(next_steps, 1):
                print_with_style(f"  {i}. {step}", "cyan")
    except FileNotFoundError as e:
        # This case is for when the script file itself is not found
        print_error_message(f"{operation_name} failed: {e}")
        raise typer.Exit(1) from None
    except subprocess.CalledProcessError as e:
        # This case handles non-zero exit codes from the script
        print_error_message(f"{operation_name} failed with exit code {e.returncode}")
        raise typer.Exit(e.returncode) from None
