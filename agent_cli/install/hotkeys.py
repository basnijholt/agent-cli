"""Hotkey installation commands."""

from __future__ import annotations

import platform

import typer

from agent_cli.cli import app
from agent_cli.core.utils import print_with_style
from agent_cli.install.common import execute_installation_script, get_platform_script


@app.command("install-hotkeys")
def install_hotkeys(
    ctx: typer.Context,  # noqa: ARG001
    force: bool = typer.Option(False, "--force", "-f", help="Force reinstall hotkey manager"),  # noqa: ARG001, FBT003
) -> None:
    """Install system-wide hotkeys for agent-cli commands.

    Sets up the following hotkeys:

    macOS:
    - Cmd+Shift+R: Toggle voice transcription
    - Cmd+Shift+A: Autocorrect clipboard text
    - Cmd+Shift+V: Voice edit clipboard text

    Linux:
    - Super+Shift+R: Toggle voice transcription
    - Super+Shift+A: Autocorrect clipboard text
    - Super+Shift+V: Voice edit clipboard text

    Note: On macOS, you may need to grant Accessibility permissions to skhd
    in System Settings → Privacy & Security → Accessibility.
    """
    script_name = get_platform_script("setup-macos-hotkeys.sh", "setup-linux-hotkeys.sh")
    system = platform.system().lower()

    # Define post-installation steps for macOS
    post_install_callback = None
    if system == "darwin":

        def post_install_callback() -> None:
            print_with_style("\n⚠️  Important:", "yellow")
            print_with_style("If hotkeys don't work, grant Accessibility permissions:", "yellow")
            print_with_style(
                "  1. Open System Settings → Privacy & Security → Accessibility",
                "cyan",
            )
            print_with_style("  2. Add and enable 'skhd'", "cyan")

    execute_installation_script(
        script_name=script_name,
        operation_name="Set up hotkeys",
        success_message="Hotkeys installed successfully!",
    )

    # Call post-install callback if defined
    if post_install_callback is not None:
        post_install_callback()
