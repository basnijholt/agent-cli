"""Pure Python launchd service management for macOS."""

from __future__ import annotations

import contextlib
import os
import plistlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent_cli.install.service_config import (
    SERVICES,
    ServiceConfig,
    install_uv,
)
from agent_cli.install.service_config import (
    find_uv as _find_uv_base,
)

# Re-export for interface compatibility
__all__ = [
    "SERVICES",
    "InstallResult",
    "ServiceConfig",
    "ServiceStatus",
    "UninstallResult",
    "check_uv_installed",
    "get_log_command",
    "get_log_dir",
    "get_service_status",
    "install_service",
    "install_uv",
    "uninstall_service",
]


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


def get_log_dir(service_name: str) -> Path:
    """Get log directory for a service."""
    return _get_log_dir(service_name)


def get_log_command(service_name: str) -> str:
    """Get command to view logs for a service."""
    log_dir = _get_log_dir(service_name)
    return f"tail -f {log_dir}/*.log"


def _find_uv() -> Path | None:
    """Find uv executable, preferring system paths over virtualenv."""
    # macOS-specific paths (Homebrew)
    macos_paths = [Path("/opt/homebrew/bin/uv")]
    return _find_uv_base(extra_paths=macos_paths)


def _generate_plist(
    service: ServiceConfig,
    uv_path: Path,
    home_dir: Path,
    log_dir: Path,
) -> dict:
    """Generate plist dictionary for a launchd service."""
    # Build command arguments
    program_args = [
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

    return {
        "Label": _get_label(service.name),
        "ProgramArguments": program_args,
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(home_dir),
        "StandardOutPath": str(log_dir / "stdout.log"),
        "StandardErrorPath": str(log_dir / "stderr.log"),
    }


@dataclass
class ServiceStatus:
    """Status of a launchd service."""

    name: str
    installed: bool
    running: bool
    pid: int | None = None


def _get_ollama_status() -> ServiceStatus:
    """Get status of Ollama via brew services."""
    installed = shutil.which("ollama") is not None

    if not installed:
        return ServiceStatus(name="ollama", installed=False, running=False)

    # Check brew services status
    result = subprocess.run(
        ["brew", "services", "list"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )

    running = False
    pid = None
    for line in result.stdout.splitlines():
        if line.startswith("ollama "):
            running = "started" in line
            # Try to get PID from pgrep
            if running:
                pid_result = subprocess.run(
                    ["pgrep", "-x", "ollama"],  # noqa: S607
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if pid_result.returncode == 0:
                    with contextlib.suppress(ValueError):
                        pid = int(pid_result.stdout.strip().split()[0])
            break

    return ServiceStatus(name="ollama", installed=True, running=running, pid=pid)


def get_service_status(service_name: str) -> ServiceStatus:
    """Get the status of a launchd service."""
    # Handle external services
    if service_name in SERVICES and SERVICES[service_name].external:
        if service_name == "ollama":
            return _get_ollama_status()
        return ServiceStatus(name=service_name, installed=False, running=False)

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


@dataclass
class InstallResult:
    """Result of installing a service."""

    success: bool
    message: str
    log_dir: Path | None = None


def _install_ollama() -> InstallResult:
    """Install and start Ollama via Homebrew."""
    if not shutil.which("brew"):
        return InstallResult(
            success=False,
            message="Homebrew not found. Install from https://brew.sh/ or install Ollama manually from https://ollama.ai",
        )

    # Install ollama if not present
    if not shutil.which("ollama"):
        try:
            subprocess.run(["brew", "install", "ollama"], check=True)  # noqa: S607
        except subprocess.CalledProcessError as e:
            return InstallResult(success=False, message=f"Failed to install Ollama: {e}")

    # Start as brew service
    try:
        subprocess.run(["brew", "services", "start", "ollama"], check=True)  # noqa: S607
        return InstallResult(success=True, message="Installed and started via Homebrew")
    except subprocess.CalledProcessError as e:
        return InstallResult(success=False, message=f"Failed to start Ollama service: {e}")


def install_service(service_name: str) -> InstallResult:
    """Install a service as a macOS launchd service.

    Returns an InstallResult with success status and message.
    """
    if service_name not in SERVICES:
        return InstallResult(
            success=False,
            message=f"Unknown service '{service_name}'. Available: {', '.join(SERVICES.keys())}",
        )

    service = SERVICES[service_name]

    # Handle external services (like ollama)
    if service.external:
        if service_name == "ollama":
            return _install_ollama()
        return InstallResult(success=False, message=f"Unknown external service: {service_name}")

    # Find uv
    uv_path = _find_uv()
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


@dataclass
class UninstallResult:
    """Result of uninstalling a service."""

    success: bool
    message: str
    was_running: bool = False


def _uninstall_ollama() -> UninstallResult:
    """Stop Ollama brew service (does not uninstall the binary)."""
    if not shutil.which("ollama"):
        return UninstallResult(success=True, message="Ollama was not installed", was_running=False)

    # Stop the service
    result = subprocess.run(
        ["brew", "services", "stop", "ollama"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    was_running = result.returncode == 0

    return UninstallResult(
        success=True,
        message="Ollama service stopped" if was_running else "Ollama service was not running",
        was_running=was_running,
    )


def uninstall_service(service_name: str) -> UninstallResult:
    """Uninstall a launchd service.

    Returns an UninstallResult with success status and message.
    """
    # Handle external services
    if service_name in SERVICES and SERVICES[service_name].external:
        if service_name == "ollama":
            return _uninstall_ollama()
        return UninstallResult(success=True, message="Service was not installed", was_running=False)

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


def check_uv_installed() -> tuple[bool, Path | None]:
    """Check if uv is installed (with macOS-specific paths)."""
    uv_path = _find_uv()
    return (uv_path is not None, uv_path)


# install_uv is imported from service_config
