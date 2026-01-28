"""Service installation and management commands."""

from __future__ import annotations

import os
import subprocess

import typer

from agent_cli.cli import app
from agent_cli.core.utils import console, print_error_message, print_with_style
from agent_cli.install.common import (
    execute_installation_script,
    get_platform_script,
    get_script_path,
)


@app.command("install-services", rich_help_panel="Installation")
def install_services() -> None:
    """Install all required services (Ollama, Whisper, Piper, OpenWakeWord).

    This command installs the following services:

    - **Ollama** - Local LLM server for text processing
    - **Wyoming Faster Whisper** - Speech-to-text transcription
    - **Wyoming Piper** - Text-to-speech synthesis
    - **Wyoming OpenWakeWord** - Wake word detection ("ok nabu", etc.)

    The appropriate installation method is used based on your operating system
    (Homebrew on macOS, apt/pip on Linux).

    **Requirements:**

    - macOS: Homebrew must be installed
    - Linux: Requires sudo access for system packages

    **Examples:**

    Install all services:
        `agent-cli install-services`

    **After installation:**

    1. Start the services: `agent-cli start-services`
    2. Test transcription: `agent-cli transcribe --list-devices`
    3. Set up hotkeys (optional): `agent-cli install-hotkeys`
    """
    script_name = get_platform_script("setup-macos.sh", "setup-linux.sh")

    execute_installation_script(
        script_name=script_name,
        operation_name="Install services",
        success_message="Services installed successfully!",
        next_steps=[
            "Start services: agent-cli start-services",
            "Set up hotkeys: agent-cli install-hotkeys",
        ],
    )


@app.command("start-services", rich_help_panel="Service Management")
def start_services(
    attach: bool = typer.Option(
        True,  # noqa: FBT003
        "--attach/--no-attach",
        help=(
            "Attach to the Zellij session after starting. "
            "With `--no-attach`, services start in background and you can "
            "reattach later with `zellij attach agent-cli`"
        ),
    ),
) -> None:
    """Start all agent-cli services in a Zellij session.

    Starts these services, each in its own Zellij pane:

    - **Ollama** - LLM server (port 11434)
    - **Wyoming Whisper** - Speech-to-text (port 10300)
    - **Wyoming Piper** - Text-to-speech (port 10200)
    - **Wyoming OpenWakeWord** - Wake word detection (port 10400)

    Services run in a Zellij terminal multiplexer session named `agent-cli`.
    If a session already exists, the command attaches to it instead of
    starting new services.

    **Keyboard shortcuts:**
    - `Ctrl-O d` - Detach (keeps services running in background)
    - `Ctrl-Q` - Quit (stops all services)
    - `Alt + arrows` - Navigate between panes

    **Examples:**

    Start services and attach:
        `agent-cli start-services`

    Start in background (for scripts or automation):
        `agent-cli start-services --no-attach`

    Reattach to running services:
        `zellij attach agent-cli`
    """
    try:
        script_path = get_script_path("start-all-services.sh")
    except FileNotFoundError as e:
        print_error_message("Service scripts not found")
        console.print(str(e))
        raise typer.Exit(1) from None

    env = os.environ.copy()
    if not attach:
        env["AGENT_CLI_NO_ATTACH"] = "true"

    try:
        subprocess.run([str(script_path)], check=True, env=env)
        if not attach:
            print_with_style("✅ Services started in background.", "green")
            print_with_style("Run 'zellij attach agent-cli' to view the session.", "yellow")
        else:
            # If we get here with attach=True, user likely detached
            print_with_style("\n👋 Detached from Zellij session.")
            print_with_style(
                "Services are still running. Use 'zellij attach agent-cli' to reattach.",
            )
    except subprocess.CalledProcessError as e:
        print_error_message(f"Failed to start services. Exit code: {e.returncode}")
        raise typer.Exit(e.returncode) from None
