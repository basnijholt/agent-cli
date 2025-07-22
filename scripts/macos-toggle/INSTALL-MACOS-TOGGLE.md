# macOS Transcription Toggle - Installation Guide

## 🚀 Automated Installation (Recommended)

The easiest way to set up the transcription toggle system:

```bash
# Run the automated setup script
./setup-macos-transcription.sh
```

This script will:
- ✅ Install terminal-notifier (notifications)
- ✅ Install skhd.zig (modern hotkey manager)
- ✅ Configure hotkey binding (Cmd+Shift+R)
- ✅ Set up accessibility permissions
- ✅ Test the complete system

## ✅ Problem Solved: Why notifications didn't work

**Issue**: Terminal doesn't have notification permissions for `osascript`
**Solution**: Use `terminal-notifier` which works independently

## Manual Installation (Advanced Users)

### 1. Install terminal-notifier (if not already installed):
```bash
brew install terminal-notifier
```

### 2. Install a hotkey manager - Choose one:

**Option A: skhd.zig (Modern, recommended)**
```bash
# Install skhd.zig
brew tap jackielii/tap
brew install jackielii/tap/skhd-zig

# Create config directory
mkdir -p ~/.config/skhd

# Add hotkey configuration
echo 'cmd + shift - r : /path/to/agent-cli/scripts/macos-toggle/toggle-transcription-best.sh' >> ~/.config/skhd/skhdrc

# Start skhd service
skhd --start-service
```

**Option B: Hammerspoon (More powerful)**
```bash
# Install Hammerspoon
brew install --cask hammerspoon

# Create config directory
mkdir -p ~/.hammerspoon

# Add this to ~/.hammerspoon/init.lua:
cat >> ~/.hammerspoon/init.lua << 'EOF'
-- Agent-CLI transcription toggle
hs.hotkey.bind({"cmd", "shift"}, "r", function()
    hs.execute("/Users/bas.nijholt/Work/agent-cli/scripts/toggle-transcription-best.sh")
end)
EOF

# Launch Hammerspoon
open -a Hammerspoon
```

### 3. Test the setup:
```bash
# Test notifications work:
terminal-notifier -title "Test" -message "This should work!" -sound Glass

# Test the toggle script:
/Users/bas.nijholt/Work/agent-cli/scripts/toggle-transcription-best.sh
```

## Usage

1. **Start transcription**: Press `Cmd+Shift+R`
   - You'll see: "🎙️ Transcription Started - Listening in background..."

2. **Stop transcription**: Press `Cmd+Shift+R` again
   - You'll see: "🛑 Transcription Stopped - Processing results..."

3. **Get result**: After processing completes
   - You'll see: "📄 Transcription Result" with the transcribed text
   - Text is automatically copied to your clipboard

## Features

✅ **Smart notifications**: Uses `terminal-notifier` (reliable) with `osascript` fallback
✅ **Error handling**: Shows specific errors if agent-cli or services aren't running
✅ **Multiple sounds**: Different notification sounds for start/stop/result/error
✅ **Path detection**: Automatically finds agent-cli in common install locations
✅ **Clipboard integration**: Results automatically copied to clipboard
✅ **Background processing**: Non-blocking operation

## Troubleshooting

**No notifications appearing?**
1. Install terminal-notifier: `brew install terminal-notifier`
2. Test: `terminal-notifier -title "Test" -message "Hello"`

**Hotkey not working?**
1. Check if skhd is running: `brew services list | grep skhd`
2. Restart skhd: `brew services restart skhd`
3. Grant accessibility permissions in System Settings

**agent-cli not found?**
1. Check installation: `which agent-cli`
2. Install: `uv tool install agent-cli`
3. Add to PATH if needed

## Customization

**Change hotkey**: Edit `~/.config/skhd/skhdrc` and change the key combination:
```bash
# Examples:
cmd + shift - t : /path/to/toggle-transcription-best.sh        # Cmd+Shift+T
alt + shift - r : /path/to/toggle-transcription-best.sh        # Alt+Shift+R
ctrl + alt - r : /path/to/toggle-transcription-best.sh         # Ctrl+Alt+R
```

**Change sounds**: Edit the script and modify the sound names:
- Available sounds: `Basso`, `Blow`, `Bottle`, `Frog`, `Funk`, `Glass`, `Hero`, `Morse`, `Ping`, `Pop`, `Purr`, `Sosumi`, `Submarine`, `Tink`

This setup replicates your Linux/Hyprland workflow perfectly on macOS! 🎉
