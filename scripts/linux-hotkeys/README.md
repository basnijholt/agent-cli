# Linux Hotkeys

System-wide hotkeys for agent-cli voice AI features on Linux.

## Setup

```bash
./setup-linux-hotkeys.sh
```

## Usage

- **`Super+Shift+R`** → Toggle voice transcription (start/stop with result)
- **`Super+Shift+A`** → Autocorrect clipboard text
- **`Super+Shift+V`** → Toggle voice edit mode for clipboard

Results appear in notifications and clipboard.

## Desktop Environment Support

- **Hyprland**: Automatic configuration via `hyprland.conf`
- **GNOME**: Automatic configuration via `gsettings`
- **Sway**: Automatic configuration via `sway/config`
- **i3**: Automatic configuration via `i3/config`
- **KDE**: Manual setup required (instructions provided)
- **XFCE**: Manual setup required (instructions provided)
- **Other**: Fallback to `xbindkeys` (automatic)

## Features

- **Cross-desktop compatibility**: Works on most Linux desktop environments
- **Wayland support**: Includes clipboard syncing for Wayland compositors
- **Fallback notifications**: Uses `notify-send`, `dunstify`, or console output
- **Automatic PATH handling**: Finds agent-cli regardless of installation method

## Troubleshooting

**Hotkeys not working?**
- Check your desktop's keyboard shortcut settings for conflicts
- Run the setup script again to reconfigure

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
