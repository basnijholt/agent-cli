"""Common utilities for installation commands."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from agent_cli.core.utils import console, print_error_message, print_with_style

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
    msg = (
        "Scripts directory not found.\n\n"
        "This might be a packaging issue. Please report this at:\n"
        "https://github.com/basnijholt/agent-cli/issues"
    )
    raise FileNotFoundError(msg)


def get_script_path(script_name: str) -> Path:
    """Get the path to a script in the scripts directory."""
    script_dir = _script_directory()
    script_path = script_dir / script_name

    if not script_path.exists():
        msg = (
            f"Script '{script_name}' not found in {script_dir}.\n\n"
            "This might be a packaging issue. Please report this at:\n"
            "https://github.com/basnijholt/agent-cli/issues"
        )
        raise FileNotFoundError(msg)

    return script_path


def _run_script(script_path: Path, check: bool = True) -> CompletedProcess[str]:
    """Run a shell script."""
    if not script_path.exists():
        msg = f"Script not found: {script_path}"
        raise FileNotFoundError(msg)

    # Make sure the script is executable
    script_path.chmod(0o755)

    # Run the script
    return subprocess.run(
        [str(script_path)],
        check=check,
        text=True,
        capture_output=True,
        cwd=script_path.parent,  # Run from script directory for relative paths
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
    try:
        script_path = get_script_path(script_name)
    except FileNotFoundError as e:
        print_error_message(f"{operation_name} scripts not found")
        console.print(str(e))
        raise typer.Exit(1) from None

    print_with_style(f"🚀 Running {script_name} to {operation_name.lower()}...", "green")

    try:
        # Run the setup script
        result = _run_script(script_path, check=False)

        # Print the output
        if result.stdout:
            console.print(result.stdout)

        if result.stderr:
            console.print(result.stderr, style="red")

        if result.returncode != 0:
            print_error_message(f"{operation_name} failed with exit code {result.returncode}")
            raise typer.Exit(result.returncode)

        print_with_style(f"✅ {success_message}", "green")

        if next_steps:
            print_with_style("\nNext steps:", "yellow")
            for i, step in enumerate(next_steps, 1):
                print_with_style(f"  {i}. {step}", "cyan")

    except subprocess.CalledProcessError as e:
        print_error_message(f"{operation_name} failed: {e}")
        if e.stderr:
            console.print(e.stderr, style="red")
        raise typer.Exit(1) from None
