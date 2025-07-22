# macOS Transcription Toggle Solutions

Open-source and built-in alternatives to Keyboard Maestro for agent-cli transcription toggling.

## Quick Comparison

| Solution | Installation | Complexity | Features | Cost |
|----------|--------------|------------|----------|------|
| **skhd + osascript** | `brew install skhd` | Low | Basic notifications | Free |
| **Hammerspoon** | `brew install hammerspoon` | Medium | Rich notifications, Lua scripting | Free |
| **Karabiner-Elements** | `brew install karabiner-elements` | Medium | System-wide key remapping | Free |
| **terminal-notifier** | `brew install terminal-notifier` | Low | Enhanced notifications | Free |
| **Built-in Shortcuts** | None (macOS 12+) | High | Native integration | Free |

## Recommended Setup: skhd + osascript

**Why:** Simple, lightweight, reliable, and uses mostly built-in macOS tools.

### Installation:
```bash
# Install skhd
brew install koekeishiya/formulae/skhd

# Make script executable (already done)
chmod +x ./toggle-transcription-macos.sh

# Create skhd config directory
mkdir -p ~/.config/skhd

# Copy configuration
cat skhd-config-example >> ~/.config/skhd/skhdrc
# Edit the path to match your script location

# Start skhd service
brew services start skhd
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
