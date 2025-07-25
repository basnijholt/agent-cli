"""Common utilities for installation commands."""

from __future__ import annotations

import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from agent_cli.core.utils import console, print_error_message, print_with_style

try:
    from importlib.resources import files
except ImportError:
    files = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from subprocess import CompletedProcess

# Cache for script directories to avoid recreating temp dirs
_SCRIPT_DIR_CACHE: Path | None = None


def get_script_directory() -> Path:
    """Get the directory containing all scripts."""
    global _SCRIPT_DIR_CACHE

    if _SCRIPT_DIR_CACHE and _SCRIPT_DIR_CACHE.exists():
        return _SCRIPT_DIR_CACHE

    # First check if we're running from source (development)
    source_scripts = Path(__file__).parent.parent.parent / "scripts"
    if source_scripts.exists():
        _SCRIPT_DIR_CACHE = source_scripts
        return source_scripts

    # Check if scripts are installed at package root level (via MANIFEST.in)
    try:
        import agent_cli  # noqa: PLC0415

        package_root = Path(agent_cli.__file__).parent.parent
        installed_scripts = package_root / "scripts"
        if installed_scripts.exists():
            _SCRIPT_DIR_CACHE = installed_scripts
            return installed_scripts
    except ImportError:
        pass

    # If using importlib.resources (Python 3.9+) - for wheel installations
    if files is not None:
        try:
            # For packages installed as wheels, scripts might be in package data
            import agent_cli  # noqa: PLC0415

            package_path = Path(agent_cli.__file__).parent

            # Create a temporary directory for all scripts
            temp_dir = Path(tempfile.mkdtemp(prefix="agent_cli_scripts_"))

            # Look for scripts in the installed package location
            scripts_source = None

            # Try to find scripts in various possible locations
            for possible_location in [
                package_path.parent / "scripts",  # Adjacent to package
                package_path / "scripts",  # Inside package
            ]:
                if possible_location.exists():
                    scripts_source = possible_location
                    break

            if scripts_source:
                # Copy all scripts to temp directory
                for item in scripts_source.rglob("*"):
                    if item.is_file():
                        relative = item.relative_to(scripts_source)
                        target = temp_dir / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, target)
                        if target.suffix == ".sh":
                            target.chmod(0o755)

                _SCRIPT_DIR_CACHE = temp_dir
                return temp_dir

        except (ImportError, AttributeError):
            pass

    msg = (
        "Scripts directory not found.\n\n"
        "This might be a packaging issue. Please report this at:\n"
        "https://github.com/basnijholt/agent-cli/issues"
    )
    raise FileNotFoundError(msg)


def get_script_path(script_name: str) -> Path:
    """Get the path to a script in the scripts directory."""
    script_dir = get_script_directory()
    script_path = script_dir / script_name

    if not script_path.exists():
        msg = (
            f"Script '{script_name}' not found in {script_dir}.\n\n"
            "This might be a packaging issue. Please report this at:\n"
            "https://github.com/basnijholt/agent-cli/issues"
        )
        raise FileNotFoundError(msg)

    return script_path


def run_script(script_path: Path, check: bool = True) -> CompletedProcess[str]:
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
        result = run_script(script_path, check=False)

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
