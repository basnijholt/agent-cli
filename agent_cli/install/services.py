"""Service installation and management commands."""

from __future__ import annotations

import os
import platform
import shutil
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


@app.command("install-services")
def install_services(
    ctx: typer.Context,  # noqa: ARG001
    force: bool = typer.Option(False, "--force", "-f", help="Force reinstall all services"),  # noqa: ARG001, FBT003
) -> None:
    """Install all required services (Ollama, Whisper, Piper, OpenWakeWord).

    This command installs:
    - Ollama (local LLM server)
    - Wyoming Faster Whisper (speech-to-text)
    - Wyoming Piper (text-to-speech)
    - Wyoming OpenWakeWord (wake word detection)

    The appropriate installation method is used based on your operating system.
    """
    system = platform.system().lower()

    if system == "darwin":
        script_name = "setup-macos.sh"
    elif system == "linux":
        script_name = "setup-linux.sh"
    else:
        print_error_message(f"Unsupported operating system: {system}")
        raise typer.Exit(1) from None

    try:
        script_path = _get_script_path(script_name)
    except FileNotFoundError as e:
        print_error_message("Installation scripts not found")
        console.print(str(e))
        raise typer.Exit(1) from None

    print_with_style(f"🚀 Running {script_name} to install services...", "green")

    try:
        # Run the setup script
        result = _run_script(script_path, check=False)

        # Print the output
        if result.stdout:
            console.print(result.stdout)

        if result.stderr:
            console.print(result.stderr, style="red")

        if result.returncode != 0:
            print_error_message(f"Installation failed with exit code {result.returncode}")
            raise typer.Exit(result.returncode)

        print_with_style("✅ Services installed successfully!", "green")
        print_with_style("\nNext steps:", "yellow")
        print_with_style("  1. Start services: agent-cli start-services", "cyan")
        print_with_style("  2. Set up hotkeys: agent-cli install-hotkeys", "cyan")

    except subprocess.CalledProcessError as e:
        print_error_message(f"Installation failed: {e}")
        if e.stderr:
            console.print(e.stderr, style="red")
        raise typer.Exit(1) from None


@app.command("start-services")
def start_services(
    ctx: typer.Context,  # noqa: ARG001
    attach: bool = typer.Option(
        True,  # noqa: FBT003
        "--attach/--no-attach",
        help="Attach to Zellij session after starting",
    ),
) -> None:
    """Start all agent-cli services in a Zellij session.

    This starts:
    - Ollama (LLM server)
    - Wyoming Faster Whisper (speech-to-text)
    - Wyoming Piper (text-to-speech)
    - Wyoming OpenWakeWord (wake word detection)

    Services run in a Zellij terminal multiplexer session named 'agent-cli'.
    Use Ctrl-Q to quit or Ctrl-O d to detach from the session.
    """
    try:
        script_path = _get_script_path("start-all-services.sh")
    except FileNotFoundError as e:
        print_error_message("Service scripts not found")
        console.print(str(e))
        raise typer.Exit(1) from None

    # Check if zellij is installed
    if not shutil.which("zellij"):
        print_error_message("Zellij is not installed.")
        print_with_style("\nInstall Zellij first:", "yellow")
        if platform.system().lower() == "darwin":
            print_with_style("  brew install zellij", "cyan")
        else:
            print_with_style("  uvx dotbins get zellij-org/zellij", "cyan")
        raise typer.Exit(1) from None

    print_with_style("🚀 Starting all services in Zellij...", "green")

    if not attach:
        # Start in detached mode
        env = os.environ.copy()
        env["ZELLIJ_AUTO_ATTACH"] = "false"
        subprocess.run([str(script_path)], check=False, env=env)
        print_with_style("✅ Services started in background.", "green")
        print_with_style("Run 'zellij attach agent-cli' to view the session.", "yellow")
    else:
        # Run the script directly (it will attach)
        try:
            subprocess.run([str(script_path)], check=True)
        except subprocess.CalledProcessError as e:
            print_error_message(f"Failed to start services: {e}")
            raise typer.Exit(1) from None
        except KeyboardInterrupt:
            # This is normal when detaching from Zellij
            print_with_style("\n👋 Detached from Zellij session.", "yellow")
            print_with_style(
                "Services are still running. Use 'zellij attach agent-cli' to reattach.",
                "cyan",
            )
