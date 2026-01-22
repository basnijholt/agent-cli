"""Service installation and management commands."""

from __future__ import annotations

import os
import platform
import subprocess
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from types import ModuleType

import typer
from rich.panel import Panel
from rich.table import Table

from agent_cli.cli import app
from agent_cli.core.utils import console, print_error_message, print_with_style
from agent_cli.install.common import get_script_path
from agent_cli.install.service_config import SERVICES

if TYPE_CHECKING:
    from agent_cli.install.service_config import ServiceConfig


def _get_service_manager() -> ModuleType:
    """Get the platform-specific service manager module."""
    system = platform.system()
    if system == "Darwin":
        from agent_cli.install import launchd  # noqa: PLC0415

        return launchd
    if system == "Linux":
        from agent_cli.install import systemd  # noqa: PLC0415

        return systemd
    print_error_message(f"Unsupported platform: {system}")
    raise typer.Exit(1)


def _get_status_str(installed: bool, running: bool) -> str:
    """Get display string for service status."""
    if running:
        return "[green]running[/green]"
    if installed:
        return "[yellow]installed[/yellow]"
    return "[dim]not installed[/dim]"


def _parse_service_selection(
    response: str,
    service_names: list[str],
    valid_services: dict[str, ServiceConfig],
) -> list[str]:
    """Parse user input into a list of service names."""
    selected = []
    for raw_part in response.split(","):
        part = raw_part.strip()
        if not part:
            continue
        try:
            idx = int(part)
            if 1 <= idx <= len(service_names):
                selected.append(service_names[idx - 1])
            else:
                console.print(f"[yellow]Warning: Invalid number {idx}, skipping[/yellow]")
        except ValueError:
            if part in valid_services:
                selected.append(part)
            else:
                console.print(f"[yellow]Warning: Unknown service '{part}', skipping[/yellow]")
    return selected


def _display_service_table(
    services: dict[str, ServiceConfig],
    title: str,
    *,
    filter_installed: bool = False,
) -> list[str]:
    """Display service selection table and return list of service names shown."""
    manager = _get_service_manager()

    console.print()
    console.print(f"[bold]{title}[/bold]")
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3)
    table.add_column("Service", style="cyan", width=20)
    table.add_column("Description", width=45)
    table.add_column("Status", width=15)

    if filter_installed:
        items = [(n, s) for n, s in services.items() if manager.get_service_status(n).installed]
    else:
        items = list(services.items())

    for i, (name, svc) in enumerate(items, 1):
        status = manager.get_service_status(name)
        status_str = _get_status_str(status.installed, status.running)
        table.add_row(str(i), svc.display_name, svc.description, status_str)

    console.print(table)
    console.print()
    return [name for name, _ in items]


def _prompt_user_selection(service_names: list[str], valid_services: dict) -> list[str]:
    """Prompt user for service selection and return selected names."""
    try:
        response = console.input(
            "[bold]Enter service numbers (comma-separated) or 'all' [all]: [/bold]",
        ).strip()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Cancelled.[/dim]")
        raise typer.Exit(0) from None

    if not response or response.lower() == "all":
        return service_names

    return _parse_service_selection(response, service_names, valid_services)


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
    manager = _get_service_manager()

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


def _ensure_ollama_installed(no_confirm: bool) -> None:
    """Ensure Ollama is installed, prompting user if needed."""
    manager = _get_service_manager()

    ollama_installed, ollama_path = manager.check_ollama_installed()
    if ollama_installed:
        console.print(f"  [green]✓[/green] Ollama installed at {ollama_path}")
        return

    console.print()
    console.print(
        "[yellow]Ollama is not installed. It's required for local LLM inference.[/yellow]",
    )

    if not no_confirm and not _confirm_action("Install Ollama now?"):
        console.print("[dim]Skipping Ollama installation.[/dim]")
        console.print(
            "[yellow]Install manually from https://ollama.ai/[/yellow]",
        )
        return

    console.print("Installing Ollama...")
    success, msg = manager.install_ollama()
    if success:
        console.print(f"  [green]✓[/green] {msg}")
        # Start Ollama service
        console.print("Starting Ollama service...")
        success, msg = manager.start_ollama_service()
        if success:
            console.print(f"  [green]✓[/green] {msg}")
        else:
            console.print(f"  [yellow]![/yellow] {msg}")
    else:
        console.print(f"  [red]✗[/red] {msg}")
        console.print("[yellow]Install manually from https://ollama.ai/[/yellow]")


@app.command("install-services", rich_help_panel="Installation")
def install_services(  # noqa: PLR0912, PLR0915, C901
    services: Annotated[
        list[str] | None,
        typer.Argument(
            help="Services to install (whisper, tts, transcription-proxy). "
            "Omit for interactive selection.",
        ),
    ] = None,
    all_services: Annotated[
        bool,
        typer.Option("--all", "-a", help="Install all available services"),
    ] = False,
    deps_only: Annotated[
        bool,
        typer.Option("--deps-only", help="Only install dependencies (uv, optionally Ollama)"),
    ] = False,
    skip_deps: Annotated[
        bool,
        typer.Option("--skip-deps", help="Skip dependency installation"),
    ] = False,
    install_ollama: Annotated[
        bool,
        typer.Option("--ollama", help="Also install/check Ollama for local LLM inference"),
    ] = False,
    no_confirm: Annotated[
        bool,
        typer.Option("--no-confirm", "-y", help="Skip confirmation prompts"),
    ] = False,
) -> None:
    """Install agent-cli server services as background services.

    This command installs agent-cli's built-in servers to run automatically
    at login and restart on failure.

    **Supported platforms:**
    - **macOS**: launchd services (~/.local/Library/LaunchAgents/)
    - **Linux**: systemd user services (~/.config/systemd/user/)

    **Available services:**
    - **whisper**: Speech-to-text ASR server (ports 10300/10301)
    - **tts**: Text-to-speech with Kokoro (ports 10200/10201)
    - **transcription-proxy**: Proxy for ASR providers (port 61337)

    Services run via `uv tool run` and don't require a virtual environment.

    **Optional dependencies:**
    - Use `--ollama` to also install Ollama for local LLM inference

    **Examples:**

        # Interactive selection (shows menu)
        agent-cli install-services

        # Install specific services
        agent-cli install-services whisper tts

        # Install all services with Ollama
        agent-cli install-services --all --ollama

        # Only install dependencies (uv, optionally Ollama)
        agent-cli install-services --deps-only --ollama

        # Skip confirmation prompts
        agent-cli install-services whisper -y

    After installation, check status with:
        agent-cli server status
    """
    manager = _get_service_manager()

    # Handle deps-only mode
    if deps_only:
        console.print("[bold]Checking dependencies...[/bold]")
        uv_installed, uv_path = manager.check_uv_installed()
        if uv_installed:
            console.print(f"  [green]✓[/green] uv already installed at {uv_path}")
        else:
            console.print("  Installing uv...")
            success, msg = manager.install_uv()
            if success:
                console.print(f"  [green]✓[/green] {msg}")
            else:
                console.print(f"  [red]✗[/red] {msg}")
                raise typer.Exit(1)
        if install_ollama:
            _ensure_ollama_installed(no_confirm)
        return

    # Determine which services to install
    if all_services:
        selected_services = list(SERVICES.keys())
    elif services:
        invalid = [s for s in services if s not in SERVICES]
        if invalid:
            print_error_message(
                f"Unknown service(s): {', '.join(invalid)}. "
                f"Available: {', '.join(SERVICES.keys())}",
            )
            raise typer.Exit(1)
        selected_services = services
    else:
        service_names = _display_service_table(SERVICES, "Select services to install:")
        selected_services = _prompt_user_selection(service_names, SERVICES)
        if not selected_services:
            console.print("[dim]No services selected.[/dim]")
            raise typer.Exit(0)

    # Check dependencies
    if not skip_deps:
        _ensure_uv_installed(no_confirm)
        if install_ollama:
            _ensure_ollama_installed(no_confirm)

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
            f"Check status: [cyan]agent-cli server status[/cyan]\n{log_hint}",
            title="Installation Complete",
            border_style="green",
        )
        console.print(panel)
    elif success_count > 0:
        panel = Panel(
            f"[yellow]Installed {success_count} service(s), "
            f"{len(failed)} failed: {', '.join(failed)}[/yellow]\n\n"
            "Check status: [cyan]agent-cli server status[/cyan]",
            title="Partial Installation",
            border_style="yellow",
        )
        console.print(panel)
    else:
        print_error_message(f"All installations failed: {', '.join(failed)}")
        raise typer.Exit(1)


@app.command("uninstall-services", rich_help_panel="Installation")
def uninstall_services(
    services: Annotated[
        list[str] | None,
        typer.Argument(
            help="Services to uninstall (whisper, tts, transcription-proxy). "
            "Omit for interactive selection.",
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
    """Uninstall agent-cli server services.

    This stops services and removes their configuration.
    Log files are preserved for debugging (macOS only).

    **Examples:**

        # Interactive selection
        agent-cli uninstall-services

        # Uninstall specific services
        agent-cli uninstall-services whisper tts

        # Uninstall all services
        agent-cli uninstall-services --all

    """
    manager = _get_service_manager()

    # Determine which services to uninstall
    if all_services:
        selected_services = [n for n in SERVICES if manager.get_service_status(n).installed]
        if not selected_services:
            console.print("[dim]No services are currently installed.[/dim]")
            return
    elif services:
        invalid = [s for s in services if s not in SERVICES]
        if invalid:
            print_error_message(
                f"Unknown service(s): {', '.join(invalid)}. "
                f"Available: {', '.join(SERVICES.keys())}",
            )
            raise typer.Exit(1)
        selected_services = services
    else:
        # Interactive selection - show only installed services
        installed = {n: s for n, s in SERVICES.items() if manager.get_service_status(n).installed}
        if not installed:
            console.print("[dim]No services are currently installed.[/dim]")
            return

        service_names = _display_service_table(
            SERVICES,
            "Select services to uninstall:",
            filter_installed=True,
        )
        selected_services = _prompt_user_selection(service_names, installed)
        if not selected_services:
            console.print("[dim]No services selected.[/dim]")
            return

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
