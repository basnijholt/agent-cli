# Linux Hotkeys

System-wide hotkeys for agent-cli voice AI features on Linux.

## Setup

```bash
./setup-linux-hotkeys.sh
```

The setup script will:
1. Install notification support if missing
2. Show you the exact hotkey bindings to add to your desktop environment
3. Provide copy-paste ready configuration for popular desktop environments

## Usage

- **`Super+Shift+R`** → Toggle voice transcription (start/stop with result)
- **`Super+Shift+A`** → Autocorrect clipboard text
- **`Super+Shift+V`** → Toggle voice edit mode for clipboard

Results appear in notifications and clipboard.

## Desktop Environment Support

The setup script provides copy-paste ready instructions for:

- **Hyprland**: Add bindings to `~/.config/hypr/hyprland.conf`
- **Sway**: Add bindings to `~/.config/sway/config`
- **i3**: Add bindings to `~/.config/i3/config`
- **GNOME**: Use Settings → Keyboard → Custom Shortcuts
- **KDE**: Use System Settings → Shortcuts → Custom Shortcuts
- **XFCE**: Use Settings Manager → Keyboard → Application Shortcuts
- **Other**: Manual hotkey configuration in your desktop environment

## Features

- **Manual configuration**: Simple setup with clear instructions for each desktop environment
- **Wayland support**: Includes clipboard syncing for Wayland compositors
- **Fallback notifications**: Uses `notify-send`, `dunstify`, or console output
- **Error handling**: Shows notifications for both success and failure cases
- **PATH handling**: Scripts automatically find agent-cli installation

## Troubleshooting

**Hotkeys not working?**
- Check your desktop's keyboard shortcut settings for conflicts
- Make sure you added the bindings to your desktop environment's config
- Verify the script paths are correct

**No notifications?**
```bash
sudo apt install libnotify-bin  # Ubuntu/Debian
sudo dnf install libnotify      # Fedora/RHEL
sudo pacman -S libnotify        # Arch
```

**Services not running?**
```bash
./start-all-services.sh
```

That's it! System-wide hotkeys for agent-cli on Linux.
