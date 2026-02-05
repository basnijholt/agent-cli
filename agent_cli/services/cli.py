"""CLI commands for service installation and management.

Manage agent-cli server services as background processes:
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
from agent_cli.install.service_config import SERVICES, get_service_manager

app = typer.Typer(
    name="services",
    help="""Manage agent-cli servers as background services.

Install, uninstall, and monitor agent-cli servers running as system services
(launchd on macOS, systemd on Linux).

**Available services:**

| Service | Description | Ports |
|---------|-------------|-------|
| `whisper` | Speech-to-text ASR | 10300/10301 |
| `tts` | Text-to-speech (Kokoro) | 10200/10201 |
| `transcription-proxy` | ASR provider proxy | 61337 |

**Examples:**

```bash
# Install whisper as a background service
agent-cli services install whisper

# Check status of all services
agent-cli services status

# Uninstall a service
agent-cli services uninstall whisper
```

Services run via `uv tool run` and start automatically at login.
""",
    add_completion=True,
    rich_markup_mode="markdown",
    no_args_is_help=True,
)
main_app.add_typer(app, name="services", rich_help_panel="Servers")


@app.command("status")
def status_cmd(
    service: Annotated[
        str | None,
        typer.Argument(
            help="Service to check, or omit for all services",
        ),
    ] = None,
) -> None:
    """Check status of installed services.

    Shows whether each service is installed and running.

    Examples:
        # Check all services
        agent-cli services status

        # Check specific service
        agent-cli services status whisper

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

    console.print()
    system = platform.system()
    if system == "Darwin":
        console.print("[dim]Log locations: ~/Library/Logs/agent-cli-<service>/[/dim]")
    else:
        console.print("[dim]Log locations: journalctl --user -u agent-cli-<service>[/dim]")


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
            help="Services to install (whisper, tts, transcription-proxy).",
        ),
    ] = None,
    all_services: Annotated[
        bool,
        typer.Option("--all", "-a", help="Install all available services"),
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
    """Install server services as background services.

    Installs agent-cli's built-in servers to run automatically
    at login and restart on failure.

    **Supported platforms:**
    - **macOS**: launchd services (~/Library/LaunchAgents/)
    - **Linux**: systemd user services (~/.config/systemd/user/)

    **Available services:**
    - **whisper**: Speech-to-text ASR server (ports 10300/10301)
    - **tts**: Text-to-speech with Kokoro (ports 10200/10201)
    - **transcription-proxy**: Proxy for ASR providers (port 61337)

    Services run via `uv tool run` and don't require a virtual environment.

    **Examples:**

        # Install specific services
        agent-cli services install whisper tts

        # Install all services
        agent-cli services install --all

        # Skip confirmation prompts
        agent-cli services install whisper -y

    After installation, check status with:
        agent-cli services status
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
        selected_services = list(SERVICES.keys())
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
            f"[green]Successfully installed {success_count} service(s)![/green]\n\n"
            f"Check status: [cyan]agent-cli services status[/cyan]\n{log_hint}",
            title="Installation Complete",
            border_style="green",
        )
        console.print(panel)
    elif success_count > 0:
        panel = Panel(
            f"[yellow]Installed {success_count} service(s), "
            f"{len(failed)} failed: {', '.join(failed)}[/yellow]\n\n"
            "Check status: [cyan]agent-cli services status[/cyan]",
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
            help="Services to uninstall (whisper, tts, transcription-proxy).",
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
    """Uninstall server services.

    Stops services and removes their configuration.
    Log files are preserved for debugging (macOS only).

    **Examples:**

        # Uninstall specific services
        agent-cli services uninstall whisper tts

        # Uninstall all services
        agent-cli services uninstall --all

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
