"""CLI commands for daemon installation and management.

Manage agent-cli servers as background daemons:
- macOS: launchd services (~/Library/LaunchAgents/)
- Linux: systemd user services (~/.config/systemd/user/)
"""

from __future__ import annotations

import platform
from typing import Annotated

import typer
from rich.panel import Panel

from agent_cli.cli import app as main_app
from agent_cli.core.utils import console, err_console
from agent_cli.install.service_config import (
    SERVICES,
    get_default_services,
    get_service_manager,
)

app = typer.Typer(
    name="daemon",
    help="""Manage agent-cli servers as background daemons.

Install, uninstall, and monitor agent-cli servers running as system daemons
(launchd on macOS, systemd on Linux).

**Available daemons:**

| Daemon | Description | Ports |
|--------|-------------|-------|
| `whisper` | Speech-to-text ASR | 10300/10301 |
| `tts-kokoro` | Text-to-speech (GPU) | 10200/10201 |
| `tts-piper` | Text-to-speech (CPU) | 10200/10201 |
| `transcription-proxy` | ASR provider proxy | 61337 |
| `memory` | Long-term memory proxy | 8100 |
| `rag` | Document retrieval proxy | 8000 |

**Examples:**

```bash
# Install whisper as a background daemon
agent-cli daemon install whisper

# Install GPU-accelerated TTS
agent-cli daemon install tts-kokoro

# Check status of all daemons
agent-cli daemon status

# Uninstall a daemon
agent-cli daemon uninstall whisper
```

Daemons run via `uv tool run` and start automatically at login.
""",
    add_completion=True,
    rich_markup_mode="markdown",
    no_args_is_help=True,
)
main_app.add_typer(app, name="daemon", rich_help_panel="Servers")


@app.command("status")
def status_cmd(
    service: Annotated[
        str | None,
        typer.Argument(
            help="Service to check, or omit for all services",
        ),
    ] = None,
    logs: Annotated[
        int,
        typer.Option(
            "--logs",
            "-l",
            help="Number of recent log lines to show (0 to disable)",
        ),
    ] = 10,
) -> None:
    """Check status of installed daemons.

    Shows whether each daemon is installed and running, along with recent log output.

    Examples:
        # Check all daemons
        agent-cli daemon status

        # Check specific daemon
        agent-cli daemon status whisper

        # Show more log lines
        agent-cli daemon status tts-kokoro --logs 20

        # Hide logs
        agent-cli daemon status --logs 0

    """
    try:
        manager = get_service_manager()
    except RuntimeError as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1) from None

    services_to_check = [service] if service else list(SERVICES.keys())

    if service and service not in SERVICES:
        err_console.print(
            f"[bold red]Error:[/bold red] Unknown service '{service}'. "
            f"Available: {', '.join(SERVICES.keys())}",
        )
        raise typer.Exit(1)

    console.print("[bold]Service Status[/bold]")
    console.print()

    for svc_name in services_to_check:
        status = manager.get_service_status(svc_name)
        if not status.installed:
            console.print(f"  {svc_name}: [dim]not installed[/dim]")
        elif status.running:
            console.print(f"  {svc_name}: [green]running[/green] (pid {status.pid})")
        else:
            console.print(f"  {svc_name}: [yellow]installed but not running[/yellow]")

        # Show recent logs for installed services
        if logs > 0 and status.installed:
            log_lines = manager.get_recent_logs(svc_name, logs)
            if log_lines:
                console.print()
                console.print(f"  [dim]Recent logs ({len(log_lines)} lines):[/dim]")
                max_line_width = 120
                for line in log_lines:
                    # Truncate long lines for readability
                    display_line = (
                        line[:max_line_width] + "..." if len(line) > max_line_width else line
                    )
                    console.print(f"    [dim]{display_line}[/dim]")
            elif status.running:
                console.print()
                console.print("  [dim]No recent logs available[/dim]")

    console.print()
    system = platform.system()
    if system == "Darwin":
        console.print("[dim]Full logs: ~/Library/Logs/agent-cli-<service>/[/dim]")
    else:
        console.print("[dim]Full logs: journalctl --user -u agent-cli-<service> -f[/dim]")


def _confirm_action(message: str) -> bool:
    """Ask user for confirmation. Returns True if confirmed."""
    try:
        confirm = console.input(f"[bold]{message} [Y/n]: [/bold]").strip().lower()
        return not confirm or confirm == "y"
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Cancelled.[/dim]")
        raise typer.Exit(0) from None


def _ensure_uv_installed(no_confirm: bool) -> None:
    """Ensure uv is installed, prompting user if needed."""
    try:
        manager = get_service_manager()
    except RuntimeError as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1) from None

    uv_installed, uv_path = manager.check_uv_installed()
    if uv_installed:
        console.print(f"  [green]✓[/green] uv installed at {uv_path}")
        return

    console.print()
    console.print("[yellow]uv is not installed. It's required for running services.[/yellow]")

    if not no_confirm and not _confirm_action("Install uv now?"):
        console.print("[dim]Skipping uv installation.[/dim]")
        console.print(
            "[yellow]Services may not work without uv. "
            "Install from https://docs.astral.sh/uv/[/yellow]",
        )
        return

    console.print("Installing uv...")
    success, msg = manager.install_uv()
    if success:
        console.print(f"  [green]✓[/green] {msg}")
    else:
        console.print(f"  [red]✗[/red] {msg}")
        raise typer.Exit(1)


@app.command("install")
def install_cmd(  # noqa: PLR0912, PLR0915
    services: Annotated[
        list[str] | None,
        typer.Argument(
            help="Services to install (whisper, tts-kokoro, tts-piper, transcription-proxy, memory, rag).",
        ),
    ] = None,
    all_services: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Install all services (auto-selects tts-kokoro on GPU, tts-piper on CPU)",
        ),
    ] = False,
    skip_deps: Annotated[
        bool,
        typer.Option("--skip-deps", help="Skip uv dependency check"),
    ] = False,
    no_confirm: Annotated[
        bool,
        typer.Option("--no-confirm", "-y", help="Skip confirmation prompts"),
    ] = False,
) -> None:
    """Install server daemons as background processes.

    Installs agent-cli's built-in servers to run automatically
    at login and restart on failure.

    **Supported platforms:**
    - **macOS**: launchd services (~/Library/LaunchAgents/)
    - **Linux**: systemd user services (~/.config/systemd/user/)

    **Available daemons:**
    - **whisper**: Speech-to-text ASR server (ports 10300/10301)
    - **tts-kokoro**: Text-to-speech with Kokoro/GPU (ports 10200/10201)
    - **tts-piper**: Text-to-speech with Piper/CPU (ports 10200/10201)
    - **transcription-proxy**: Proxy for ASR providers (port 61337)
    - **memory**: Long-term memory proxy for LLMs (port 8100)
    - **rag**: Document retrieval proxy for LLMs (port 8000)

    Note: tts-kokoro and tts-piper use the same ports and are mutually exclusive.
    Use `--all` to auto-select based on your platform (kokoro on GPU, piper on CPU).

    Daemons run via `uv tool run` and don't require a virtual environment.

    **Examples:**

        # Install specific daemons
        agent-cli daemon install whisper tts-kokoro

        # Install all daemons (auto-selects TTS backend)
        agent-cli daemon install --all

        # Skip confirmation prompts
        agent-cli daemon install whisper -y

    After installation, check status with:
        agent-cli daemon status
    """
    if not services and not all_services:
        err_console.print(
            f"[bold red]Error:[/bold red] Specify services to install or use --all. "
            f"Available: {', '.join(SERVICES.keys())}",
        )
        raise typer.Exit(1)

    try:
        manager = get_service_manager()
    except RuntimeError as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1) from None

    # Determine which services to install
    if all_services:
        # Get default services (auto-selects one TTS backend based on platform)
        selected_services = get_default_services()
    else:
        assert services is not None  # Already checked above
        invalid = [s for s in services if s not in SERVICES]
        if invalid:
            err_console.print(
                f"[bold red]Error:[/bold red] Unknown service(s): {', '.join(invalid)}. "
                f"Available: {', '.join(SERVICES.keys())}",
            )
            raise typer.Exit(1)
        selected_services = services

    # Check uv dependency
    if not skip_deps:
        _ensure_uv_installed(no_confirm)

    # Confirm installation
    if not no_confirm:
        console.print()
        console.print(f"[bold]Will install:[/bold] {', '.join(selected_services)}")
        if not _confirm_action("Continue?"):
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    # Install services
    console.print()
    console.print("[bold]Installing services...[/bold]")

    success_count = 0
    failed = []

    for svc_name in selected_services:
        result = manager.install_service(svc_name)
        if result.success:
            if result.log_dir:
                console.print(
                    f"  [green]✓[/green] {svc_name}: {result.message}. Logs: {result.log_dir}/",
                )
            else:
                log_cmd = manager.get_log_command(svc_name)
                console.print(
                    f"  [green]✓[/green] {svc_name}: {result.message}. Logs: [cyan]{log_cmd}[/cyan]",
                )
            success_count += 1
        else:
            console.print(f"  [red]✗[/red] {svc_name}: {result.message}")
            failed.append(svc_name)

    # Summary
    console.print()
    system = platform.system()
    if system == "Darwin":
        log_hint = "View logs: [cyan]~/Library/Logs/agent-cli-<service>/[/cyan]"
    else:
        log_hint = "View logs: [cyan]journalctl --user -u agent-cli-<service> -f[/cyan]"

    if success_count == len(selected_services):
        panel = Panel(
            f"[green]Successfully installed {success_count} daemon(s)![/green]\n\n"
            f"Check status: [cyan]agent-cli daemon status[/cyan]\n{log_hint}",
            title="Installation Complete",
            border_style="green",
        )
        console.print(panel)
    elif success_count > 0:
        panel = Panel(
            f"[yellow]Installed {success_count} daemon(s), "
            f"{len(failed)} failed: {', '.join(failed)}[/yellow]\n\n"
            "Check status: [cyan]agent-cli daemon status[/cyan]",
            title="Partial Installation",
            border_style="yellow",
        )
        console.print(panel)
    else:
        err_console.print(
            f"[bold red]Error:[/bold red] All installations failed: {', '.join(failed)}",
        )
        raise typer.Exit(1)


@app.command("uninstall")
def uninstall_cmd(
    services: Annotated[
        list[str] | None,
        typer.Argument(
            help="Services to uninstall (whisper, tts-kokoro, tts-piper, transcription-proxy, memory, rag).",
        ),
    ] = None,
    all_services: Annotated[
        bool,
        typer.Option("--all", "-a", help="Uninstall all installed services"),
    ] = False,
    no_confirm: Annotated[
        bool,
        typer.Option("--no-confirm", "-y", help="Skip confirmation prompts"),
    ] = False,
) -> None:
    """Uninstall server daemons.

    Stops daemons and removes their configuration.
    Log files are preserved for debugging (macOS only).

    **Examples:**

        # Uninstall specific daemons
        agent-cli daemon uninstall whisper tts

        # Uninstall all daemons
        agent-cli daemon uninstall --all

    """
    if not services and not all_services:
        err_console.print(
            f"[bold red]Error:[/bold red] Specify services to uninstall or use --all. "
            f"Available: {', '.join(SERVICES.keys())}",
        )
        raise typer.Exit(1)

    try:
        manager = get_service_manager()
    except RuntimeError as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1) from None

    # Determine which services to uninstall
    if all_services:
        selected_services = [n for n in SERVICES if manager.get_service_status(n).installed]
        if not selected_services:
            console.print("[dim]No services are currently installed.[/dim]")
            return
    else:
        assert services is not None  # Already checked above
        invalid = [s for s in services if s not in SERVICES]
        if invalid:
            err_console.print(
                f"[bold red]Error:[/bold red] Unknown service(s): {', '.join(invalid)}. "
                f"Available: {', '.join(SERVICES.keys())}",
            )
            raise typer.Exit(1)
        selected_services = services

    # Confirm uninstallation
    if not no_confirm:
        console.print()
        console.print(f"[bold]Will uninstall:[/bold] {', '.join(selected_services)}")
        if not _confirm_action("Continue?"):
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    # Uninstall services
    console.print()
    console.print("[bold]Uninstalling services...[/bold]")

    for svc_name in selected_services:
        result = manager.uninstall_service(svc_name)
        console.print(f"  [green]✓[/green] {svc_name}: {result.message}")

    console.print()
    if platform.system() == "Darwin":
        console.print(
            "[dim]Note: Log files are preserved at ~/Library/Logs/agent-cli-<service>/[/dim]",
        )
