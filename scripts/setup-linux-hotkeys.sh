#!/usr/bin/env bash

set -e

echo "⌨️ Setting up Linux hotkeys..."

# Check if we're on Linux
if [[ "$(uname)" != "Linux" ]]; then
    echo "❌ This script is for Linux only"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TRANSCRIBE_SCRIPT="$SCRIPT_DIR/linux-hotkeys/toggle-transcription.sh"
AUTOCORRECT_SCRIPT="$SCRIPT_DIR/linux-hotkeys/toggle-autocorrect.sh"
VOICE_EDIT_SCRIPT="$SCRIPT_DIR/linux-hotkeys/toggle-voice-edit.sh"

# Install notifications if missing
echo "📢 Checking notifications..."
if ! command -v notify-send &> /dev/null && ! command -v dunstify &> /dev/null; then
    echo "📦 Installing notification support..."
    if command -v apt &> /dev/null; then
        sudo apt install -y libnotify-bin
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y libnotify
    elif command -v pacman &> /dev/null; then
        sudo pacman -S --noconfirm libnotify
    elif command -v zypper &> /dev/null; then
        sudo zypper install -y libnotify-tools
    else
        echo "⚠️ Please install libnotify manually for your distribution"
    fi
fi

# Test notifications
if command -v notify-send &> /dev/null; then
    notify-send "🎙️ Setup Complete" "Agent-CLI hotkeys ready!" || echo "⚠️ Notifications may not work in your environment"
elif command -v dunstify &> /dev/null; then
    dunstify "🎙️ Setup Complete" "Agent-CLI hotkeys ready!" || echo "⚠️ Notifications may not work in your environment"
fi

echo ""
echo "✅ Scripts ready! Add these hotkeys to your desktop environment:"
echo ""
echo "📋 Hotkey Bindings:"
echo "  Super+Shift+R → $TRANSCRIBE_SCRIPT"
echo "  Super+Shift+A → $AUTOCORRECT_SCRIPT"
echo "  Super+Shift+V → $VOICE_EDIT_SCRIPT"
echo ""
echo "🖥️ Configuration by Desktop Environment:"
echo ""
echo "Hyprland (~/.config/hypr/hyprland.conf):"
echo "  bind = SUPER SHIFT, R, exec, $TRANSCRIBE_SCRIPT"
echo "  bind = SUPER SHIFT, A, exec, $AUTOCORRECT_SCRIPT"
echo "  bind = SUPER SHIFT, V, exec, $VOICE_EDIT_SCRIPT"
echo ""
echo "Sway (~/.config/sway/config):"
echo "  bindsym \$mod+Shift+r exec $TRANSCRIBE_SCRIPT"
echo "  bindsym \$mod+Shift+a exec $AUTOCORRECT_SCRIPT"
echo "  bindsym \$mod+Shift+v exec $VOICE_EDIT_SCRIPT"
echo ""
echo "i3 (~/.config/i3/config):"
echo "  bindsym \$mod+Shift+r exec --no-startup-id $TRANSCRIBE_SCRIPT"
echo "  bindsym \$mod+Shift+a exec --no-startup-id $AUTOCORRECT_SCRIPT"
echo "  bindsym \$mod+Shift+v exec --no-startup-id $VOICE_EDIT_SCRIPT"
echo ""
echo "GNOME: Settings → Keyboard → View and Customize Shortcuts → Custom Shortcuts"
echo "KDE: System Settings → Shortcuts → Custom Shortcuts"
echo "XFCE: Settings Manager → Keyboard → Application Shortcuts"
echo ""
echo "For other environments, bind Super+Shift+R/A/V to the respective scripts."
