"""Hotkey installation commands."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

import typer

from agent_cli.cli import app
from agent_cli.core.utils import console, print_error_message, print_with_style


def _get_script_path(script_name: str) -> Path:
    """Get the path to a script in the scripts directory."""
    # First check if we're running from source (development)
    source_scripts = Path(__file__).parent.parent.parent / "scripts"
    if source_scripts.exists() and (source_scripts / script_name).exists():
        return source_scripts / script_name

    # When installed via uvx/pip, users should clone the repo for scripts
    # This is the expected workflow as documented in the README
    msg = (
        f"Script '{script_name}' not found.\n\n"
        "The installation scripts are not bundled with the Python package.\n"
        "Please clone the agent-cli repository to access them:\n\n"
        "  git clone https://github.com/basnijholt/agent-cli.git\n"
        "  cd agent-cli\n\n"
        "Then run the commands from within the repository directory."
    )
    raise FileNotFoundError(msg)


def _run_script(script_path: Path, check: bool = True) -> subprocess.CompletedProcess:
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
    )


@app.command("install-hotkeys")
def install_hotkeys(
    ctx: typer.Context,  # noqa: ARG001
    force: bool = typer.Option(False, "--force", "-f", help="Force reinstall hotkey manager"),  # noqa: ARG001, FBT003
) -> None:
    """Install system-wide hotkeys for agent-cli commands.

    Sets up the following hotkeys:

    macOS:
    - Cmd+Shift+R: Toggle voice transcription
    - Cmd+Shift+A: Autocorrect clipboard text
    - Cmd+Shift+V: Voice edit clipboard text

    Linux:
    - Super+Shift+R: Toggle voice transcription
    - Super+Shift+A: Autocorrect clipboard text
    - Super+Shift+V: Voice edit clipboard text

    Note: On macOS, you may need to grant Accessibility permissions to skhd
    in System Settings → Privacy & Security → Accessibility.
    """
    system = platform.system().lower()

    if system == "darwin":
        script_name = "setup-macos-hotkeys.sh"
    elif system == "linux":
        script_name = "setup-linux-hotkeys.sh"
    else:
        print_error_message(f"Unsupported operating system: {system}")
        raise typer.Exit(1) from None

    try:
        script_path = _get_script_path(script_name)
    except FileNotFoundError as e:
        print_error_message("Hotkey scripts not found")
        console.print(str(e))
        raise typer.Exit(1) from None

    print_with_style(f"⌨️  Running {script_name} to set up hotkeys...", "green")

    try:
        # Run the setup script
        result = _run_script(script_path, check=False)

        # Print the output
        if result.stdout:
            console.print(result.stdout)

        if result.stderr:
            console.print(result.stderr, style="red")

        if result.returncode != 0:
            print_error_message(f"Hotkey setup failed with exit code {result.returncode}")
            raise typer.Exit(result.returncode)

        print_with_style("✅ Hotkeys installed successfully!", "green")

        if system == "darwin":
            print_with_style("\n⚠️  Important:", "yellow")
            print_with_style("If hotkeys don't work, grant Accessibility permissions:", "yellow")
            print_with_style(
                "  1. Open System Settings → Privacy & Security → Accessibility",
                "cyan",
            )
            print_with_style("  2. Add and enable 'skhd'", "cyan")

    except subprocess.CalledProcessError as e:
        print_error_message(f"Hotkey setup failed: {e}")
        if e.stderr:
            console.print(e.stderr, style="red")
        raise typer.Exit(1) from None
