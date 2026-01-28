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
    """Install all required AI services for local voice and LLM processing.

    **What gets installed:**

    - **Ollama**: Local LLM server (preloads `gemma3:4b` model)
    - **Whisper**: Speech-to-text (MLX on Apple Silicon, faster-whisper on Linux)
    - **Piper**: Text-to-speech via Wyoming protocol
    - **OpenWakeWord**: Wake word detection via Wyoming protocol

    Also installs: `uv` (Python package manager), `zellij` (terminal multiplexer)

    **Prerequisites:**

    - macOS: Homebrew must be installed
    - Linux: PortAudio dev libraries (`sudo apt install portaudio19-dev` on Ubuntu)

    **Next steps after installation:**

    1. `agent-cli start-services` - Start all services in a Zellij session
    2. `agent-cli install-hotkeys` - Set up system hotkeys for voice commands

    **Platform notes:**

    - Apple Silicon: Uses MLX Whisper (installed as launchd service)
    - Intel Mac: Uses Linux-style faster-whisper setup
    - Linux: GPU acceleration requires NVIDIA drivers and CUDA
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
        help="Attach to Zellij session. Use `--no-attach` to start in background.",
    ),
) -> None:
    """Start all agent-cli services in a Zellij terminal multiplexer session.

    **Services started:**

    - **Ollama**: Local LLM server for chat and voice editing
    - **Whisper**: Speech-to-text transcription
    - **Piper**: Text-to-speech synthesis
    - **OpenWakeWord**: "Hey Jarvis" wake word detection

    **Session management:**

    - Services run in a Zellij session named `agent-cli`
    - Press `Ctrl-Q` to quit all services
    - Press `Ctrl-O d` to detach (services keep running)
    - Reattach with: `zellij attach agent-cli`

    **Prerequisite:** Run `agent-cli install-services` first to install the services.
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
