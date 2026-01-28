"""Hotkey installation commands."""

from __future__ import annotations

import platform

from agent_cli.cli import app
from agent_cli.core.utils import print_with_style
from agent_cli.install.common import execute_installation_script, get_platform_script


@app.command("install-hotkeys", rich_help_panel="Installation")
def install_hotkeys() -> None:
    """Install system-wide hotkeys for agent-cli commands.

    Sets up three global hotkeys:

    | Hotkey (macOS / Linux)  | Action                                          |
    |-------------------------|-------------------------------------------------|
    | Cmd/Super + Shift + R   | Toggle voice transcription (start/stop)         |
    | Cmd/Super + Shift + A   | Autocorrect clipboard text (grammar/spelling)   |
    | Cmd/Super + Shift + V   | Voice edit clipboard text (voice commands)      |

    **macOS** (fully automatic):

    1. Installs `skhd` (hotkey daemon) and `terminal-notifier` via Homebrew
    2. Creates config at `~/.config/skhd/skhdrc`
    3. Starts skhd as a background service
    4. May require Accessibility permissions: System Settings → Privacy & Security → Accessibility → enable 'skhd'

    **Linux** (manual DE configuration):

    1. Installs `libnotify` for notifications (if missing)
    2. Prints binding instructions for your desktop environment
    3. You manually add hotkeys pointing to the installed scripts

    Supported Linux DEs: Hyprland, Sway, i3, GNOME, KDE, XFCE.

    **Customizing hotkeys** (macOS): Edit `~/.config/skhd/skhdrc` and restart skhd:
    `skhd --restart-service`
    """
    script_name = get_platform_script("setup-macos-hotkeys.sh", "setup-linux-hotkeys.sh")
    system = platform.system().lower()

    execute_installation_script(
        script_name=script_name,
        operation_name="Set up hotkeys",
        success_message="Hotkeys installed successfully!",
    )

    # Post-installation steps for macOS
    if system == "darwin":
        print_with_style("\n⚠️  Important:", "yellow")
        print_with_style("If hotkeys don't work, grant Accessibility permissions:", "yellow")
        print_with_style(
            "  1. Open System Settings → Privacy & Security → Accessibility",
            "cyan",
        )
        print_with_style("  2. Add and enable 'skhd'", "cyan")
