# macOS Hotkeys

System-wide hotkeys for agent-cli voice AI features on macOS.

## Setup

```bash
./setup-macos-hotkeys.sh
```

## Usage

- **`Cmd+Shift+R`** → Toggle voice transcription (start/stop with result)
- **`Cmd+Shift+A`** → Autocorrect clipboard text
- **`Cmd+Shift+V`** → Toggle voice edit mode for clipboard

Results appear in notifications and clipboard.

## What it installs

- **skhd**: Hotkey manager
- **terminal-notifier**: Notifications
- **Configuration**: Automatic setup

## Troubleshooting

**Hotkey not working?**
- Grant accessibility permissions in System Settings

**No notifications?**
```bash
terminal-notifier -title "Test" -message "Hello"
```

**Services not running?**
```bash
./start-all-services.sh
```

That's it! System-wide hotkeys for agent-cli on macOS.
