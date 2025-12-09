"""macOS permission checker for agent-cli hotkeys."""

from __future__ import annotations

import platform
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from collections.abc import Callable

console = Console()

# Minimum supported macOS version (Monterey)
MIN_MACOS_VERSION = 12


@dataclass
class CheckResult:
    """Result of a permission check."""

    name: str
    passed: bool
    message: str
    fix: str | None = None
    info: list[str] = field(default_factory=list)
    warning: bool = False  # True if this is a warning, not a failure


def _run_command(cmd: list[str], *, timeout: int = 5) -> tuple[bool, str]:
    """Run a command and return (success, output)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.returncode == 0, result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, ""


def _check_command_exists(cmd: str) -> str | None:
    """Check if a command exists and return its path, or None."""
    return shutil.which(cmd)


def _check_process_running(name: str) -> bool:
    """Check if a process is running."""
    success, _ = _run_command(["pgrep", "-x", name])
    return success


def _check_port_open(port: int) -> bool:
    """Check if a port is accepting connections on localhost."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            return sock.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False


def _check_macos_version() -> CheckResult:
    """Check macOS version compatibility."""
    success, version = _run_command(["sw_vers", "-productVersion"])
    if not success:
        return CheckResult(
            name="macOS Version",
            passed=False,
            message="Could not determine macOS version",
        )

    major = int(version.split(".")[0])
    if major >= MIN_MACOS_VERSION:
        return CheckResult(
            name="macOS Version",
            passed=True,
            message=f"macOS {version} (supported)",
        )
    return CheckResult(
        name="macOS Version",
        passed=True,
        message=f"macOS {version}",
        warning=True,
        info=["Recommended: macOS 12 Monterey or later"],
    )


def _check_skhd_installed() -> CheckResult:
    """Check if skhd is installed."""
    path = _check_command_exists("skhd")
    if path:
        return CheckResult(name="skhd Installation", passed=True, message=f"Found at {path}")
    return CheckResult(
        name="skhd Installation",
        passed=False,
        message="skhd not installed",
        fix="Run: brew tap jackielii/tap && brew install jackielii/tap/skhd-zig",
    )


def _check_skhd_running() -> CheckResult:
    """Check if skhd service is running."""
    if _check_process_running("skhd"):
        return CheckResult(name="skhd Service", passed=True, message="Running")
    return CheckResult(
        name="skhd Service",
        passed=False,
        message="Not running",
        fix="Run: skhd --start-service",
    )


def _check_terminal_notifier() -> CheckResult:
    """Check if terminal-notifier is installed."""
    path = _check_command_exists("terminal-notifier")
    if path:
        return CheckResult(
            name="terminal-notifier",
            passed=True,
            message=f"Found at {path}",
        )
    return CheckResult(
        name="terminal-notifier",
        passed=False,
        message="Not installed",
        fix="Run: brew install terminal-notifier",
    )


def _check_agent_cli() -> CheckResult:
    """Check if agent-cli is installed and accessible."""
    # Check standard location first
    standard_path = Path.home() / ".local" / "bin" / "agent-cli"
    if standard_path.exists():
        return CheckResult(
            name="agent-cli",
            passed=True,
            message=f"Found at {standard_path}",
        )

    # Check PATH
    path = _check_command_exists("agent-cli")
    if path:
        result = CheckResult(
            name="agent-cli",
            passed=True,
            message=f"Found at {path}",
        )
        if path != str(standard_path):
            result.info.append(f"Note: Hotkey scripts expect {standard_path}")
        return result

    return CheckResult(
        name="agent-cli",
        passed=False,
        message="Not found",
        fix="Install with: uv tool install agent-cli",
    )


def _check_skhd_config() -> CheckResult:
    """Check if skhd is configured for agent-cli."""
    config_path = Path.home() / ".config" / "skhd" / "skhdrc"
    if not config_path.exists():
        return CheckResult(
            name="skhd Config",
            passed=False,
            message="Config file not found",
            fix="Run: agent-cli install-hotkeys",
        )

    content = config_path.read_text()
    if "agent-cli" in content or "agent_cli" in content:
        return CheckResult(
            name="skhd Config",
            passed=True,
            message="Hotkeys configured",
            info=[f"Config: {config_path}"],
        )

    return CheckResult(
        name="skhd Config",
        passed=True,
        message="Config exists but no agent-cli hotkeys",
        warning=True,
        fix="Run: agent-cli install-hotkeys",
    )


def _check_accessibility() -> CheckResult:
    """Check Accessibility permission status."""
    # If skhd is running, it likely has accessibility permissions
    if _check_process_running("skhd"):
        return CheckResult(
            name="Accessibility",
            passed=True,
            message="skhd is running (likely has permission)",
            info=[
                "If hotkeys don't work, verify in:",
                "System Settings → Privacy & Security → Accessibility",
            ],
        )

    return CheckResult(
        name="Accessibility",
        passed=False,
        message="Cannot verify (skhd not running)",
        fix="Start skhd first, then grant Accessibility permission if prompted",
        info=["System Settings → Privacy & Security → Accessibility"],
    )


def _check_microphone() -> CheckResult:
    """Check microphone permission using Swift."""
    # Use Swift to check AVCaptureDevice authorization status
    swift_code = """
import AVFoundation
import Foundation
switch AVCaptureDevice.authorizationStatus(for: .audio) {
case .authorized: print("authorized")
case .denied: print("denied")
case .restricted: print("restricted")
case .notDetermined: print("notDetermined")
@unknown default: print("unknown")
}
"""
    success, output = _run_command(["swift", "-e", swift_code], timeout=10)

    if not success:
        return CheckResult(
            name="Microphone",
            passed=True,
            message="Could not verify (Swift check failed)",
            warning=True,
            info=["System Settings → Privacy & Security → Microphone"],
        )

    status = output.strip()
    if status == "authorized":
        return CheckResult(
            name="Microphone",
            passed=True,
            message="Access authorized",
        )
    if status == "denied":
        return CheckResult(
            name="Microphone",
            passed=False,
            message="Access denied",
            fix="System Settings → Privacy & Security → Microphone → Enable for Terminal",
        )
    if status == "restricted":
        return CheckResult(
            name="Microphone",
            passed=False,
            message="Access restricted (MDM or parental controls)",
            info=["Contact your system administrator"],
        )
    if status == "notDetermined":
        return CheckResult(
            name="Microphone",
            passed=True,
            message="Not yet requested",
            warning=True,
            info=["Permission will be requested on first use"],
        )
    return CheckResult(
        name="Microphone",
        passed=True,
        message=f"Unknown status: {status}",
        warning=True,
    )


def _check_notifications() -> CheckResult:
    """Check notification delivery by sending a test notification."""
    notifier = _check_command_exists("terminal-notifier")
    if not notifier:
        return CheckResult(
            name="Notifications",
            passed=False,
            message="terminal-notifier not installed",
            fix="Run: brew install terminal-notifier",
        )

    # Send a test notification
    test_group = f"agent-cli-test-{id(_check_notifications)}"
    success, _ = _run_command(
        [
            notifier,
            "-title",
            "Permission Test",
            "-message",
            "If you see this, notifications work!",
            "-group",
            test_group,
            "-timeout",
            "2",
        ],
    )

    # Clean up
    _run_command([notifier, "-remove", test_group])

    if success:
        return CheckResult(
            name="Notifications",
            passed=True,
            message="Test notification sent",
            info=[
                "If you didn't see it:",
                "System Settings → Notifications → terminal-notifier",
                "Set 'Alert style' to 'Alerts' for persistent indicators",
            ],
        )
    return CheckResult(
        name="Notifications",
        passed=False,
        message="Failed to send test notification",
        fix="System Settings → Notifications → Enable for terminal-notifier",
    )


def _check_local_services() -> CheckResult:
    """Check if local AI services are accessible."""
    services = [
        (11434, "Ollama"),
        (10300, "Whisper (ASR)"),
        (10200, "Piper (TTS)"),
        (10400, "OpenWakeWord"),
    ]

    accessible = []
    for port, name in services:
        if _check_port_open(port):
            accessible.append(f"{name} (:{port})")

    if accessible:
        return CheckResult(
            name="Local Services",
            passed=True,
            message=f"{len(accessible)} service(s) running",
            info=accessible,
        )

    return CheckResult(
        name="Local Services",
        passed=True,
        message="No services detected",
        warning=True,
        info=[
            "Services may not be started yet",
            "Run: agent-cli install-services && start services",
        ],
    )


def _run_all_checks() -> tuple[list[CheckResult], int, int]:
    """Run all permission checks and return results with counts."""
    checks: list[Callable[[], CheckResult]] = [
        _check_macos_version,
        _check_skhd_installed,
        _check_skhd_running,
        _check_terminal_notifier,
        _check_agent_cli,
        _check_skhd_config,
        _check_accessibility,
        _check_microphone,
        _check_notifications,
        _check_local_services,
    ]

    results = []
    issues = 0
    warnings = 0

    for check in checks:
        result = check()
        results.append(result)
        if not result.passed:
            issues += 1
        elif result.warning:
            warnings += 1

    return results, issues, warnings


def _print_check_result(result: CheckResult) -> None:
    """Print a single check result."""
    if result.passed:
        icon = "[yellow]⚠[/yellow]" if result.warning else "[green]✓[/green]"
    else:
        icon = "[red]✗[/red]"

    console.print(f"  {icon} [bold]{result.name}[/bold]: {result.message}")

    for info in result.info:
        console.print(f"      [dim]{info}[/dim]")

    if result.fix and not result.passed:
        console.print(f"      [yellow]→ Fix:[/yellow] {result.fix}")


def _print_results(results: list[CheckResult], issues: int, warnings: int) -> None:
    """Print all check results with summary."""
    # Group results by category
    installation = results[:6]  # Version through config
    permissions = results[6:]  # Accessibility through services

    console.print()
    console.print(Panel.fit("[bold blue]Installation Checks[/bold blue]"))
    for result in installation:
        _print_check_result(result)

    console.print()
    console.print(Panel.fit("[bold blue]Permission Checks[/bold blue]"))
    for result in permissions:
        _print_check_result(result)

    # Summary
    console.print()
    if issues == 0 and warnings == 0:
        console.print("[bold green]✓ All checks passed![/bold green]")
        console.print()
        console.print("[dim]If hotkeys still don't work, try:[/dim]")
        console.print("[dim]  1. Restart skhd: skhd --restart-service[/dim]")
        console.print("[dim]  2. Log out and back in[/dim]")
    elif issues == 0:
        console.print(f"[yellow]⚠ {warnings} warning(s) - review above[/yellow]")
    else:
        console.print(f"[red]✗ {issues} issue(s), {warnings} warning(s)[/red]")
        console.print()
        console.print("[bold]Please address the issues above.[/bold]")

    # Quick reference
    console.print()
    table = Table(title="System Settings Locations", show_header=False, box=None)
    table.add_column("Setting", style="cyan")
    table.add_column("Path", style="dim")
    table.add_row("Accessibility", "Privacy & Security → Accessibility")
    table.add_row("Microphone", "Privacy & Security → Microphone")
    table.add_row("Local Network", "Privacy & Security → Local Network")
    table.add_row("Notifications", "Notifications → terminal-notifier")
    console.print(table)


def check_permissions() -> int:
    """Run permission checks and return exit code (0=ok, 1=issues)."""
    if platform.system() != "Darwin":
        console.print("[red]This command is for macOS only.[/red]")
        return 1

    console.print()
    console.print("[bold blue]Agent-CLI Permission Checker[/bold blue]")
    console.print("[dim]Diagnosing hotkey setup issues...[/dim]")

    results, issues, warnings = _run_all_checks()
    _print_results(results, issues, warnings)

    return 1 if issues > 0 else 0
