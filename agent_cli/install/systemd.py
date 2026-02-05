"""Pure Python systemd service management for Linux."""

from __future__ import annotations

import subprocess
from pathlib import Path

from agent_cli.install.service_config import (
    SERVICES,
    InstallResult,
    ServiceConfig,
    ServiceManager,
    ServiceStatus,
    UninstallResult,
    build_service_command,
    find_uv,
    install_uv,
)

# Linux-specific paths for uv
_LINUX_UV_PATHS = [Path("/usr/bin/uv")]


def _get_unit_name(service_name: str) -> str:
    """Get systemd unit name for a service."""
    return f"agent-cli-{service_name}.service"


def _get_unit_path(service_name: str) -> Path:
    """Get path to systemd unit file for a service."""
    return Path.home() / ".config" / "systemd" / "user" / _get_unit_name(service_name)


def _get_log_dir(service_name: str) -> Path:
    """Get log directory for a service (for compatibility)."""
    # systemd uses journalctl, but we provide a consistent interface
    return Path.home() / ".local" / "share" / "agent-cli" / "logs" / service_name


def _get_log_command(service_name: str) -> str:
    """Get command to view logs for a service."""
    return f"journalctl --user -u agent-cli-{service_name} -f"


def _generate_unit_file(
    service: ServiceConfig,
    uv_path: Path,
) -> str:
    """Generate systemd unit file content for a service."""
    exec_start = " ".join(build_service_command(service, uv_path))

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


def _get_service_status(service_name: str) -> ServiceStatus:
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


def _install_service(service_name: str) -> InstallResult:
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
    uv_path = find_uv(extra_paths=_LINUX_UV_PATHS)
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


def _uninstall_service(service_name: str) -> UninstallResult:
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
    status = _get_service_status(service_name)
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


def _check_uv_installed() -> tuple[bool, Path | None]:
    """Check if uv is installed (with Linux-specific paths)."""
    uv_path = find_uv(extra_paths=_LINUX_UV_PATHS)
    return (uv_path is not None, uv_path)


# Export the service manager instance
manager = ServiceManager(
    check_uv_installed=_check_uv_installed,
    install_uv=install_uv,
    install_service=_install_service,
    uninstall_service=_uninstall_service,
    get_service_status=_get_service_status,
    get_log_command=_get_log_command,
)
