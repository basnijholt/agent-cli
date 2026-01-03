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

> [!TIP]
> For a persistent "Listening…" indicator, open System Settings → Notifications → *terminal-notifier* and set the Alert style to **Persistent** (or choose **Alerts** on older macOS versions).
> Also enable "Allow notification when mirroring or sharing the display".
> The scripts keep that alert pinned while dismissing status/result notifications automatically.

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
