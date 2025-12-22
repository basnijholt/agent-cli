"""Service installation and management commands."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

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


SYSTEMD_SERVICE_TEMPLATE = """\
[Unit]
Description=Agent CLI Transcribe Daemon
After=network.target sound.target

[Service]
Type=simple
ExecStart={exec_start}
Restart=on-failure
RestartSec=5
Environment="PATH={path}"
{environment}

[Install]
WantedBy=default.target
"""


def _get_agent_cli_path() -> str:
    """Get the path to the agent-cli executable."""
    # Try to find agent-cli in PATH
    agent_cli_path = shutil.which("agent-cli")
    if agent_cli_path:
        return agent_cli_path

    # Fallback: use the Python executable with -m
    return f"{sys.executable} -m agent_cli.cli"


@app.command("install-transcribe-daemon", rich_help_panel="Installation")
def install_transcribe_daemon(
    *,
    role: str = typer.Option(
        "user",
        "--role",
        "-r",
        help="Role name for logging.",
    ),
    log_file: Path | None = typer.Option(  # noqa: B008
        None,
        "--log-file",
        "-l",
        help="Custom log file path.",
    ),
    audio_dir: Path | None = typer.Option(  # noqa: B008
        None,
        "--audio-dir",
        help="Custom audio directory.",
    ),
    llm: bool = typer.Option(
        False,  # noqa: FBT003
        "--llm/--no-llm",
        help="Enable LLM processing.",
    ),
    silence_threshold: float = typer.Option(
        1.0,
        "--silence-threshold",
        "-s",
        help="Silence threshold in seconds.",
    ),
    extra_args: str | None = typer.Option(
        None,
        "--extra-args",
        help="Additional arguments to pass to transcribe-daemon.",
    ),
    uninstall: bool = typer.Option(
        False,  # noqa: FBT003
        "--uninstall",
        help="Uninstall the systemd service.",
    ),
) -> None:
    """Install transcribe-daemon as a systemd user service.

    This creates a systemd user service that runs the transcribe-daemon
    continuously, automatically restarting on failure.

    Examples:
        # Install with defaults
        agent-cli install-transcribe-daemon

        # Install with custom role and LLM processing
        agent-cli install-transcribe-daemon --role meeting --llm

        # Uninstall the service
        agent-cli install-transcribe-daemon --uninstall

    After installation, manage with:
        systemctl --user start transcribe-daemon
        systemctl --user stop transcribe-daemon
        systemctl --user status transcribe-daemon
        journalctl --user -u transcribe-daemon -f

    """
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_file = service_dir / "transcribe-daemon.service"

    if uninstall:
        if not service_file.exists():
            print_with_style("⚠️ Service is not installed.", style="yellow")
            return

        # Stop and disable the service
        subprocess.run(
            ["systemctl", "--user", "stop", "transcribe-daemon"],  # noqa: S607
            check=False,
            capture_output=True,
        )
        subprocess.run(
            ["systemctl", "--user", "disable", "transcribe-daemon"],  # noqa: S607
            check=False,
            capture_output=True,
        )

        # Remove the service file
        service_file.unlink()
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],  # noqa: S607
            check=False,
            capture_output=True,
        )

        print_with_style("✅ Transcribe daemon service uninstalled.", style="green")
        return

    # Build the ExecStart command
    agent_cli = _get_agent_cli_path()
    cmd_parts = [agent_cli, "transcribe-daemon"]
    cmd_parts.extend(["--role", role])
    cmd_parts.extend(["--silence-threshold", str(silence_threshold)])

    if log_file:
        cmd_parts.extend(["--transcription-log", str(log_file.expanduser())])
    if audio_dir:
        cmd_parts.extend(["--audio-dir", str(audio_dir.expanduser())])
    if llm:
        cmd_parts.append("--llm")
    if extra_args:
        cmd_parts.extend(extra_args.split())

    exec_start = " ".join(cmd_parts)

    # Build environment variables
    env_lines = []
    # Pass through API keys if set
    for env_var in ["OPENAI_API_KEY", "GEMINI_API_KEY"]:
        value = os.environ.get(env_var)
        if value:
            env_lines.append(f'Environment="{env_var}={value}"')

    environment = "\n".join(env_lines)

    # Generate service file content
    service_content = SYSTEMD_SERVICE_TEMPLATE.format(
        exec_start=exec_start,
        path=os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        environment=environment,
    )

    # Create service directory and file
    service_dir.mkdir(parents=True, exist_ok=True)
    service_file.write_text(service_content)

    print_with_style(f"✅ Created service file: {service_file}", style="green")

    # Reload systemd
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],  # noqa: S607
        check=False,
        capture_output=True,
    )

    # Enable the service
    result = subprocess.run(
        ["systemctl", "--user", "enable", "transcribe-daemon"],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print_with_style("✅ Service enabled.", style="green")
    else:
        print_with_style(f"⚠️ Failed to enable service: {result.stderr}", style="yellow")

    console.print()
    print_with_style("Next steps:", style="bold")
    console.print("  Start the service:  [cyan]systemctl --user start transcribe-daemon[/cyan]")
    console.print("  Check status:       [cyan]systemctl --user status transcribe-daemon[/cyan]")
    console.print("  View logs:          [cyan]journalctl --user -u transcribe-daemon -f[/cyan]")
    console.print("  Stop the service:   [cyan]systemctl --user stop transcribe-daemon[/cyan]")
