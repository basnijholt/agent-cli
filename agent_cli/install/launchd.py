"""Pure Python launchd service management for macOS."""

from __future__ import annotations

import contextlib
import os
import plistlib
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

# macOS-specific paths for uv (Homebrew)
_MACOS_UV_PATHS = [Path("/opt/homebrew/bin/uv")]


def _get_label(service_name: str) -> str:
    """Get launchd label for a service."""
    normalized = service_name.replace("-", "_")
    return f"com.agent_cli.{normalized}"


def _get_plist_path(service_name: str) -> Path:
    """Get path to plist file for a service."""
    return Path.home() / "Library" / "LaunchAgents" / f"{_get_label(service_name)}.plist"


def _get_log_dir(service_name: str) -> Path:
    """Get log directory for a service."""
    return Path.home() / "Library" / "Logs" / f"agent-cli-{service_name}"


def _get_log_command(service_name: str) -> str:
    """Get command to view logs for a service."""
    log_dir = _get_log_dir(service_name)
    return f"tail -f {log_dir}/*.log"


def _get_recent_logs(service_name: str, num_lines: int = 10) -> list[str]:
    """Get recent log lines for a service."""
    log_dir = _get_log_dir(service_name)
    stderr_log = log_dir / "stderr.log"
    stdout_log = log_dir / "stdout.log"

    lines: list[str] = []

    # Prefer stderr as it usually has more useful info
    for log_file in [stderr_log, stdout_log]:
        if log_file.exists():
            try:
                with log_file.open() as f:
                    all_lines = f.readlines()
                    lines = [line.rstrip() for line in all_lines[-num_lines:]]
                    if lines:
                        break
            except OSError:
                continue

    return lines


def _generate_plist(
    service: ServiceConfig,
    uv_path: Path,
    home_dir: Path,
    log_dir: Path,
) -> dict:
    """Generate plist dictionary for a launchd service."""
    return {
        "Label": _get_label(service.name),
        "ProgramArguments": build_service_command(service, uv_path, use_macos_extra=True),
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(home_dir),
        "StandardOutPath": str(log_dir / "stdout.log"),
        "StandardErrorPath": str(log_dir / "stderr.log"),
    }


def _get_service_status(service_name: str) -> ServiceStatus:
    """Get the status of a launchd service."""
    plist_path = _get_plist_path(service_name)
    installed = plist_path.exists()

    if not installed:
        return ServiceStatus(name=service_name, installed=False, running=False)

    # Check if running using launchctl
    label = _get_label(service_name)
    uid = os.getuid()

    result = subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{label}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return ServiceStatus(name=service_name, installed=True, running=False)

    # Parse PID from output
    pid = None
    for line in result.stdout.splitlines():
        if "pid =" in line.lower():
            parts = line.split("=")
            if len(parts) > 1:
                with contextlib.suppress(ValueError):
                    pid = int(parts[1].strip())
                break

    running = pid is not None and pid != 0
    return ServiceStatus(
        name=service_name,
        installed=True,
        running=running,
        pid=pid if running else None,
    )


def _install_service(service_name: str) -> InstallResult:
    """Install a service as a macOS launchd service.

    Returns an InstallResult with success status and message.
    """
    if service_name not in SERVICES:
        return InstallResult(
            success=False,
            message=f"Unknown service '{service_name}'. Available: {', '.join(SERVICES.keys())}",
        )

    service = SERVICES[service_name]

    # Find uv
    uv_path = find_uv(extra_paths=_MACOS_UV_PATHS)
    if not uv_path:
        return InstallResult(
            success=False,
            message="uv not found. Install it from https://docs.astral.sh/uv/",
        )

    home_dir = Path.home()
    log_dir = _get_log_dir(service_name)
    plist_path = _get_plist_path(service_name)

    # Create directories
    log_dir.mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate and write plist
    plist_data = _generate_plist(service, uv_path, home_dir, log_dir)

    with plist_path.open("wb") as f:
        plistlib.dump(plist_data, f)

    # Unload if already loaded (ignore errors if not loaded)
    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(plist_path)],  # noqa: S607
        capture_output=True,
        check=False,
    )

    # Load the service
    result = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return InstallResult(
            success=False,
            message=f"Failed to load service: {result.stderr.strip()}",
            log_dir=log_dir,
        )

    return InstallResult(
        success=True,
        message="Installed and started",
        log_dir=log_dir,
    )


def _uninstall_service(service_name: str) -> UninstallResult:
    """Uninstall a launchd service.

    Returns an UninstallResult with success status and message.
    """
    plist_path = _get_plist_path(service_name)

    if not plist_path.exists():
        return UninstallResult(
            success=True,
            message="Service was not installed",
            was_running=False,
        )

    # Unload service
    uid = os.getuid()
    result = subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(plist_path)],  # noqa: S607
        capture_output=True,
        check=False,
    )
    was_running = result.returncode == 0

    # Remove plist file
    plist_path.unlink()

    return UninstallResult(
        success=True,
        message="Service stopped and removed" if was_running else "Service removed",
        was_running=was_running,
    )


def _check_uv_installed() -> tuple[bool, Path | None]:
    """Check if uv is installed (with macOS-specific paths)."""
    uv_path = find_uv(extra_paths=_MACOS_UV_PATHS)
    return (uv_path is not None, uv_path)


# Export the service manager instance
manager = ServiceManager(
    check_uv_installed=_check_uv_installed,
    install_uv=install_uv,
    install_service=_install_service,
    uninstall_service=_uninstall_service,
    get_service_status=_get_service_status,
    get_log_command=_get_log_command,
    get_recent_logs=_get_recent_logs,
)
