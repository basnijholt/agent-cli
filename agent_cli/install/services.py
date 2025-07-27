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

    This command installs:
    - Ollama (local LLM server)
    - Wyoming Faster Whisper (speech-to-text)
    - Wyoming Piper (text-to-speech)
    - Wyoming OpenWakeWord (wake word detection)

    The appropriate installation method is used based on your operating system.
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
