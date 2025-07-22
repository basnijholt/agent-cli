# macOS Transcription Toggle Solutions

Open-source and built-in alternatives to Keyboard Maestro for agent-cli transcription toggling.

## 🚀 Automated Setup (Recommended)

Run the automated installer:
```bash
./setup-macos-transcription.sh
```

This handles everything automatically: installs dependencies, configures hotkeys, sets permissions, and tests the system.

## Manual Setup Options

| Solution | Installation | Complexity | Features | Cost |
|----------|--------------|------------|----------|------|
| **skhd.zig + terminal-notifier** | `brew install skhd-zig terminal-notifier` | Low | Modern hotkeys, reliable notifications | Free |
| **Hammerspoon** | `brew install hammerspoon` | Medium | Rich notifications, Lua scripting | Free |
| **Karabiner-Elements** | `brew install karabiner-elements` | Medium | System-wide key remapping | Free |
| **Built-in Shortcuts** | None (macOS 12+) | High | Native integration | Free |

## Recommended Manual Setup: skhd.zig + terminal-notifier

**Why:** Modern, actively maintained, fully compatible with original skhd, and uses reliable terminal-notifier for notifications.

### Installation:
```bash
# Install skhd.zig and terminal-notifier
brew tap jackielii/tap
brew install jackielii/tap/skhd-zig terminal-notifier

# Create skhd config directory
mkdir -p ~/.config/skhd

# Copy configuration
cat skhd-config-example >> ~/.config/skhd/skhdrc
# Edit the path to match your script location

# Start skhd service
skhd --start-service
```

### Usage:
- Press **Cmd+Shift+R** to start/stop transcription
- Notifications will appear in macOS Notification Center
- Results are automatically copied to clipboard

## Alternative: Hammerspoon (Most Powerful)

If you want more advanced features and don't mind Lua scripting:

```bash
# Install Hammerspoon
brew install --cask hammerspoon

# Copy the Lua script to Hammerspoon config
mkdir -p ~/.hammerspoon
cp hammerspoon-transcription.lua ~/.hammerspoon/init.lua

# Launch Hammerspoon and enable accessibility permissions
open -a Hammerspoon
```

## Files Included:

- `toggle-transcription-macos.sh` - Main toggle script using osascript
- `toggle-transcription-terminal-notifier.sh` - Enhanced version with terminal-notifier
- `skhd-config-example` - skhd configuration example
- `hammerspoon-transcription.lua` - Hammerspoon Lua script
- `transcription-toggle.applescript` - AppleScript version
- `karabiner-config-example.json` - Karabiner-Elements configuration
- `shortcuts-app-instructions.md` - Built-in Shortcuts app setup

## Key Differences from Linux/Hyprland:

✅ **Same functionality:** Process detection with `pgrep`, signal handling with `pkill -INT`
✅ **Same workflow:** Toggle start/stop, background processing, result notification
⚙️ **Different notifications:** `osascript` or `terminal-notifier` instead of `notify-send`
⚙️ **Different clipboard:** `pbcopy` instead of `wl-copy`
⚙️ **Different key binding:** Various options instead of Hyprland binds

## Troubleshooting:

- **Permissions**: Grant accessibility permissions to your chosen hotkey manager
- **PATH issues**: Scripts include common agent-cli installation paths
- **Service not starting**: Use `brew services restart <service>` to restart services
- **Notifications not showing**: Check System Preferences → Notifications settings

Choose the solution that best fits your needs! The skhd option is recommended for most users.
