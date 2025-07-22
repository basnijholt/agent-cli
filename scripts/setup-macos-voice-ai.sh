#!/bin/bash

set -e

echo "🎙️ Setting up macOS voice AI toggles..."

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ This script is for macOS only"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
if ! command -v brew &> /dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

brew install terminal-notifier
brew tap jackielii/tap && brew install jackielii/tap/skhd-zig

# Setup configuration
echo "⚙️ Setting up configuration..."
mkdir -p ~/.config/skhd

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRANSCRIBE_SCRIPT="$SCRIPT_DIR/macos-toggle/toggle-transcription.sh"
AUTOCORRECT_SCRIPT="$SCRIPT_DIR/macos-toggle/toggle-autocorrect.sh"
VOICE_EDIT_SCRIPT="$SCRIPT_DIR/macos-toggle/toggle-voice-edit.sh"

cat > ~/.config/skhd/skhdrc << EOF
# Agent-CLI Voice AI Toggles
cmd + shift - r : "$TRANSCRIBE_SCRIPT"
cmd + shift - a : "$AUTOCORRECT_SCRIPT"
cmd + shift - v : "$VOICE_EDIT_SCRIPT"
EOF

# Start service
echo "🚀 Starting skhd..."
skhd --start-service

# Test
echo "🧪 Testing..."
terminal-notifier -title "🎙️ Setup Complete" -message "Voice AI hotkeys ready!"

echo ""
echo "✅ Done! Hotkeys:"
echo "  Cmd+Shift+R - Transcribe voice"
echo "  Cmd+Shift+A - Autocorrect clipboard"
echo "  Cmd+Shift+V - Voice edit clipboard"
echo ""
echo "If the hotkey doesn't work:"
echo "1. Open System Settings → Privacy & Security → Accessibility"
echo "2. Add and enable 'skhd'"
