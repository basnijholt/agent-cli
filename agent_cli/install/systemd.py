"""Pure Python systemd service management for Linux."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent_cli.install.service_config import (
    SERVICES,
    ServiceConfig,
    check_ollama_installed,
    find_uv,
    install_uv,
)

# Re-export for interface compatibility
__all__ = [
    "SERVICES",
    "InstallResult",
    "ServiceConfig",
    "ServiceStatus",
    "UninstallResult",
    "check_ollama_installed",
    "check_uv_installed",
    "get_log_command",
    "get_log_dir",
    "get_service_status",
    "install_ollama",
    "install_service",
    "install_uv",
    "start_ollama_service",
    "uninstall_service",
]


def _get_unit_name(service_name: str) -> str:
    """Get systemd unit name for a service."""
    return f"agent-cli-{service_name}.service"


def _get_unit_path(service_name: str) -> Path:
    """Get path to systemd unit file for a service."""
    return Path.home() / ".config" / "systemd" / "user" / _get_unit_name(service_name)


def get_log_dir(service_name: str) -> Path:
    """Get log directory for a service (for compatibility)."""
    # systemd uses journalctl, but we provide a consistent interface
    return Path.home() / ".local" / "share" / "agent-cli" / "logs" / service_name


def get_log_command(service_name: str) -> str:
    """Get command to view logs for a service."""
    return f"journalctl --user -u agent-cli-{service_name} -f"


def _find_uv() -> Path | None:
    """Find uv executable, preferring system paths over virtualenv."""
    # Linux-specific paths
    linux_paths = [Path("/usr/bin/uv")]
    return find_uv(extra_paths=linux_paths)


def _generate_unit_file(
    service: ServiceConfig,
    uv_path: Path,
) -> str:
    """Generate systemd unit file content for a service."""
    # Build command
    exec_start_args = [
        str(uv_path),
        "tool",
        "run",
        "--from",
        f"agent-cli[{service.extra}]",
        "agent-cli",
        "server",
        service.name,
        *service.command_args,
    ]
    exec_start = " ".join(exec_start_args)

    return f"""[Unit]
Description=agent-cli {service.display_name}
After=network.target

[Service]
ExecStart={exec_start}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


@dataclass
class ServiceStatus:
    """Status of a systemd service."""

    name: str
    installed: bool
    running: bool
    pid: int | None = None


def get_service_status(service_name: str) -> ServiceStatus:
    """Get the status of a systemd service."""
    unit_path = _get_unit_path(service_name)
    installed = unit_path.exists()

    if not installed:
        return ServiceStatus(name=service_name, installed=False, running=False)

    # Check if running using systemctl
    unit_name = _get_unit_name(service_name)
    result = subprocess.run(
        ["systemctl", "--user", "is-active", unit_name],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )

    running = result.returncode == 0 and result.stdout.strip() == "active"

    # Get PID if running
    pid = None
    if running:
        pid_result = subprocess.run(
            ["systemctl", "--user", "show", unit_name, "--property=MainPID"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if pid_result.returncode == 0:
            # Output is like "MainPID=12345"
            line = pid_result.stdout.strip()
            if "=" in line:
                try:
                    pid = int(line.split("=")[1])
                    if pid == 0:
                        pid = None
                except ValueError:
                    pass

    return ServiceStatus(
        name=service_name,
        installed=True,
        running=running,
        pid=pid,
    )


@dataclass
class InstallResult:
    """Result of installing a service."""

    success: bool
    message: str
    log_dir: Path | None = None


def install_service(service_name: str) -> InstallResult:
    """Install a service as a Linux systemd user service.

    Returns an InstallResult with success status and message.
    """
    if service_name not in SERVICES:
        return InstallResult(
            success=False,
            message=f"Unknown service '{service_name}'. Available: {', '.join(SERVICES.keys())}",
        )

    service = SERVICES[service_name]

    # Find uv
    uv_path = _find_uv()
    if not uv_path:
        return InstallResult(
            success=False,
            message="uv not found. Install it from https://docs.astral.sh/uv/",
        )

    unit_path = _get_unit_path(service_name)
    unit_name = _get_unit_name(service_name)

    # Create directories
    unit_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate and write unit file
    unit_content = _generate_unit_file(service, uv_path)
    unit_path.write_text(unit_content)

    # Stop service if running (ignore errors if not running)
    subprocess.run(
        ["systemctl", "--user", "stop", unit_name],  # noqa: S607
        capture_output=True,
        check=False,
    )

    # Reload systemd to pick up new/changed unit file
    result = subprocess.run(
        ["systemctl", "--user", "daemon-reload"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return InstallResult(
            success=False,
            message=f"Failed to reload systemd: {result.stderr.strip()}",
        )

    # Enable service
    result = subprocess.run(
        ["systemctl", "--user", "enable", unit_name],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return InstallResult(
            success=False,
            message=f"Failed to enable service: {result.stderr.strip()}",
        )

    # Start service
    result = subprocess.run(
        ["systemctl", "--user", "start", unit_name],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return InstallResult(
            success=False,
            message=f"Failed to start service: {result.stderr.strip()}",
        )

    return InstallResult(
        success=True,
        message="Installed and started",
        log_dir=None,  # systemd uses journalctl, not file-based logs
    )


@dataclass
class UninstallResult:
    """Result of uninstalling a service."""

    success: bool
    message: str
    was_running: bool = False


def uninstall_service(service_name: str) -> UninstallResult:
    """Uninstall a systemd user service.

    Returns an UninstallResult with success status and message.
    """
    unit_path = _get_unit_path(service_name)
    unit_name = _get_unit_name(service_name)

    if not unit_path.exists():
        return UninstallResult(
            success=True,
            message="Service was not installed",
            was_running=False,
        )

    # Check if running before stopping
    status = get_service_status(service_name)
    was_running = status.running

    # Stop service
    subprocess.run(
        ["systemctl", "--user", "stop", unit_name],  # noqa: S607
        capture_output=True,
        check=False,
    )

    # Disable service
    subprocess.run(
        ["systemctl", "--user", "disable", unit_name],  # noqa: S607
        capture_output=True,
        check=False,
    )

    # Remove unit file
    unit_path.unlink()

    # Reload systemd
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],  # noqa: S607
        capture_output=True,
        check=False,
    )

    return UninstallResult(
        success=True,
        message="Service stopped and removed" if was_running else "Service removed",
        was_running=was_running,
    )


def check_uv_installed() -> tuple[bool, Path | None]:
    """Check if uv is installed (with Linux-specific paths)."""
    uv_path = _find_uv()
    return (uv_path is not None, uv_path)


# install_uv and check_ollama_installed are imported from service_config


def install_ollama() -> tuple[bool, str]:
    """Install Ollama using the official installer (Linux).

    Returns (success, message).
    """
    try:
        # Use the official Ollama installer
        result = subprocess.run(
            ["curl", "-fsSL", "https://ollama.ai/install.sh"],  # noqa: S607
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["sh"],  # noqa: S607
            input=result.stdout,
            capture_output=True,
            text=True,
            check=True,
        )
        return True, "Ollama installed successfully"
    except subprocess.CalledProcessError as e:
        return False, f"Failed to install Ollama: {e}"


def start_ollama_service() -> tuple[bool, str]:
    """Start Ollama as a systemd service.

    Returns (success, message).
    """
    # First try user service, then system service
    result = subprocess.run(
        ["systemctl", "--user", "start", "ollama"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return True, "Ollama started as user service"

    # Try system service
    result = subprocess.run(
        ["systemctl", "start", "ollama"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return True, "Ollama started as system service"

    # Fall back to starting ollama serve in background
    # (the official installer may set up the service differently)
    result = subprocess.run(
        ["ollama", "serve"],  # noqa: S607
        capture_output=True,
        check=False,
        start_new_session=True,
    )
    return True, "Ollama started (run 'ollama serve' to keep it running)"
