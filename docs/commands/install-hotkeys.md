---
icon: lucide/keyboard
---

# install-hotkeys

Install system-wide hotkeys for agent-cli.

## Usage

```bash
agent-cli install-hotkeys
```

## Description

Sets up system-wide hotkeys to control `agent-cli` from anywhere on your system.

### macOS (via skhd)
- **Cmd+Shift+R**: Toggle voice transcription
- **Cmd+Shift+A**: Autocorrect clipboard text
- **Cmd+Shift+V**: Voice edit clipboard text

### Linux (via desktop environment)
- **Super+Shift+R**: Toggle voice transcription
- **Super+Shift+A**: Autocorrect clipboard text
- **Super+Shift+V**: Voice edit clipboard text

## Notes

- On **macOS**, you may need to grant Accessibility permissions to `skhd` in System Settings → Privacy & Security → Accessibility.
- On **Linux**, support depends on your desktop environment (GNOME, KDE, Hyprland, Sway, i3).
