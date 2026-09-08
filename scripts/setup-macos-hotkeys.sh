#!/usr/bin/env bash

set -e

echo "⌨️ Setting up macOS hotkeys..."

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ This script is for macOS only"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
if ! command -v brew &> /dev/null; then
    echo "🍺 Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

brew install terminal-notifier
brew tap jackielii/tap && brew install jackielii/tap/skhd-zig

REREGISTER_SKHD_SERVICE=0

patch_skhd_microphone_usage() {
    local app_path
    app_path="$(brew --prefix skhd-zig)/skhd.app"

    if [[ ! -d "$app_path" ]]; then
        return
    fi

    if /usr/libexec/PlistBuddy -c "Print :NSMicrophoneUsageDescription" "$app_path/Contents/Info.plist" >/dev/null 2>&1; then
        return
    fi

    echo "🎙️ Adding microphone usage description to skhd.app..."
    plutil -insert NSMicrophoneUsageDescription \
        -string "skhd launches agent-cli voice transcription hotkeys that record from the microphone." \
        "$app_path/Contents/Info.plist"
    codesign --force --deep --sign - "$app_path" >/dev/null
    tccutil reset Microphone com.jackielii.skhd >/dev/null 2>&1 || true
    tccutil reset Accessibility com.jackielii.skhd >/dev/null 2>&1 || true
    tccutil reset ListenEvent com.jackielii.skhd >/dev/null 2>&1 || true
    REREGISTER_SKHD_SERVICE=1
}

patch_skhd_microphone_usage

# Setup configuration
echo "⚙️ Setting up configuration..."
mkdir -p ~/.config/skhd

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRANSCRIBE_SCRIPT="$SCRIPT_DIR/macos-hotkeys/toggle-transcription.sh"
AUTOCORRECT_SCRIPT="$SCRIPT_DIR/macos-hotkeys/toggle-autocorrect.sh"
VOICE_EDIT_SCRIPT="$SCRIPT_DIR/macos-hotkeys/toggle-voice-edit.sh"

cat > ~/.config/skhd/skhdrc << EOF
# Agent-CLI Hotkeys
cmd + shift - r : "$TRANSCRIBE_SCRIPT"
cmd + shift - a : "$AUTOCORRECT_SCRIPT"
cmd + shift - v : "$VOICE_EDIT_SCRIPT"
EOF

# Start service
echo "🚀 Starting skhd..."
if [[ "$REREGISTER_SKHD_SERVICE" = "1" ]]; then
    skhd --uninstall-service >/dev/null 2>&1 || true
fi
skhd --start-service

# Test
echo "🧪 Testing..."
terminal-notifier -title "⌨️ Setup Complete" -message "Agent-CLI hotkeys ready!"

echo ""
echo "✅ Done! Hotkeys:"
echo "  Cmd+Shift+R - Transcribe voice"
echo "  Cmd+Shift+A - Autocorrect clipboard"
echo "  Cmd+Shift+V - Voice edit clipboard"
echo ""
echo "If the hotkey doesn't work:"
echo "1. Open System Settings → Privacy & Security → Accessibility"
echo "2. Add and enable 'skhd'"
echo "3. If prompted, allow Microphone access for 'skhd'"
echo ""
echo "If the notification doesn't show:"
echo "1. Open System Settings → Notifications"
echo "2. Find 'terminal-notifier' and allow notifications"
echo "3. Set Alert style to Persistent for better visibility"
echo "4. Enable 'Allow notification when mirroring or sharing the display'"
