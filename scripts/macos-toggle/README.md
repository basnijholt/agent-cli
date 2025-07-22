# macOS Voice Transcription Toggle

Press one key to start/stop voice transcription, just like the Linux version.

## Setup

```bash
./setup-macos-transcription.sh
```

## Usage

- **Press `Cmd+Shift+R`** → Start transcription
- **Press `Cmd+Shift+R`** → Stop and get result
- Result appears in notification and clipboard

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

That's it! Simple voice transcription toggle for macOS.
