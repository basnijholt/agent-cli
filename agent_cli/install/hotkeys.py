"""Hotkey installation commands."""

from __future__ import annotations

import platform
from typing import Annotated

import typer

from agent_cli.cli import app
from agent_cli.core.utils import print_with_style
from agent_cli.install.common import execute_installation_script, get_platform_script
from agent_cli.install.permissions import check_permissions


@app.command("install-hotkeys", rich_help_panel="Installation")
def install_hotkeys(
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            "-c",
            help="Check permissions and diagnose issues instead of installing.",
        ),
    ] = False,
) -> None:
    """Install system-wide hotkeys for agent-cli commands.

    Sets up the following hotkeys:

    **macOS:**
    - Cmd+Shift+R: Toggle voice transcription
    - Cmd+Shift+A: Autocorrect clipboard text
    - Cmd+Shift+V: Voice edit clipboard text

    **Linux:**
    - Super+Shift+R: Toggle voice transcription
    - Super+Shift+A: Autocorrect clipboard text
    - Super+Shift+V: Voice edit clipboard text

    **Troubleshooting:**

    If hotkeys don't work on macOS, run `agent-cli install-hotkeys --check`
    to diagnose permission issues.
    """
    system = platform.system().lower()

    # Check mode: diagnose permissions
    if check:
        if system != "darwin":
            print_with_style("Permission checking is currently only available for macOS.", "yellow")
            raise typer.Exit(0)

        exit_code = check_permissions()
        raise typer.Exit(exit_code)

    # Install mode
    script_name = get_platform_script("setup-macos-hotkeys.sh", "setup-linux-hotkeys.sh")

    execute_installation_script(
        script_name=script_name,
        operation_name="Set up hotkeys",
        success_message="Hotkeys installed successfully!",
    )

    # Post-installation: run permission check on macOS
    if system == "darwin":
        print_with_style("\n🔍 Running permission check...", "blue")
        check_permissions()
