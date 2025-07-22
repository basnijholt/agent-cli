#!/bin/bash

set -e

echo "⌨️ Setting up Linux hotkeys..."

# Check if we're on Linux
if [[ "$(uname)" != "Linux" ]]; then
    echo "❌ This script is for Linux only"
    exit 1
fi

# Make scripts executable
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "$SCRIPT_DIR/linux-hotkeys/"*.sh

TRANSCRIBE_SCRIPT="$SCRIPT_DIR/linux-hotkeys/toggle-transcription.sh"
AUTOCORRECT_SCRIPT="$SCRIPT_DIR/linux-hotkeys/toggle-autocorrect.sh"
VOICE_EDIT_SCRIPT="$SCRIPT_DIR/linux-hotkeys/toggle-voice-edit.sh"

# Function to detect desktop environment
detect_desktop() {
    if [ -n "$XDG_CURRENT_DESKTOP" ]; then
        echo "$XDG_CURRENT_DESKTOP"
    elif [ -n "$DESKTOP_SESSION" ]; then
        echo "$DESKTOP_SESSION"
    elif [ -n "$WAYLAND_DISPLAY" ] && command -v hyprctl &> /dev/null; then
        echo "Hyprland"
    elif [ -n "$SWAYSOCK" ]; then
        echo "sway"
    elif command -v gnome-shell &> /dev/null; then
        echo "GNOME"
    elif command -v kwin_x11 &> /dev/null || command -v kwin_wayland &> /dev/null; then
        echo "KDE"
    elif command -v xfce4-session &> /dev/null; then
        echo "XFCE"
    else
        echo "Unknown"
    fi
}

# Function to set up notifications
setup_notifications() {
    echo "📢 Checking notifications..."
    if command -v notify-send &> /dev/null; then
        echo "✅ notify-send is available"
        notify-send "🎙️ Test" "Notifications working!" || echo "⚠️ notify-send found but not working"
    elif command -v dunstify &> /dev/null; then
        echo "✅ dunstify is available"
        dunstify "🎙️ Test" "Notifications working!" || echo "⚠️ dunstify found but not working"
    else
        echo "⚠️ No notification system found. Install libnotify:"
        echo "  Ubuntu/Debian: sudo apt install libnotify-bin"
        echo "  Fedora/RHEL: sudo dnf install libnotify"
        echo "  Arch: sudo pacman -S libnotify"
    fi
}

# Function to configure hotkeys based on desktop environment
configure_hotkeys() {
    local desktop="$1"
    echo "🖥️ Detected desktop: $desktop"

    case "$desktop" in
        *"Hyprland"*|*"hyprland"*)
            configure_hyprland
            ;;
        *"GNOME"*|*"gnome"*)
            configure_gnome
            ;;
        *"KDE"*|*"kde"*|*"plasma"*)
            configure_kde
            ;;
        *"sway"*)
            configure_sway
            ;;
        *"XFCE"*|*"xfce"*)
            configure_xfce
            ;;
        *"i3"*)
            configure_i3
            ;;
        *)
            configure_generic
            ;;
    esac
}

configure_hyprland() {
    echo "⚙️ Configuring Hyprland hotkeys..."
    local config_file="$HOME/.config/hypr/hyprland.conf"

    if [ ! -f "$config_file" ]; then
        echo "❌ Hyprland config not found at $config_file"
        echo "Please add these bindings manually to your Hyprland config:"
        show_hotkey_bindings "hyprland"
        return
    fi

    # Backup existing config
    cp "$config_file" "$config_file.backup.$(date +%s)"

    # Add hotkey bindings
    echo "" >> "$config_file"
    echo "# Agent-CLI hotkeys" >> "$config_file"
    echo "bind = SUPER SHIFT, R, exec, $TRANSCRIBE_SCRIPT" >> "$config_file"
    echo "bind = SUPER SHIFT, A, exec, $AUTOCORRECT_SCRIPT" >> "$config_file"
    echo "bind = SUPER SHIFT, V, exec, $VOICE_EDIT_SCRIPT" >> "$config_file"

    echo "✅ Added hotkeys to Hyprland config"
    echo "↻ Reload Hyprland with: hyprctl reload"
}

configure_gnome() {
    echo "⚙️ Configuring GNOME hotkeys..."

    # Set up custom keybindings using gsettings
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/transcribe/', '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/autocorrect/', '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voice-edit/']"

    # Transcribe hotkey
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/transcribe/ name 'Agent-CLI Transcribe'
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/transcribe/ command "$TRANSCRIBE_SCRIPT"
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/transcribe/ binding '<Super><Shift>r'

    # Autocorrect hotkey
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/autocorrect/ name 'Agent-CLI Autocorrect'
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/autocorrect/ command "$AUTOCORRECT_SCRIPT"
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/autocorrect/ binding '<Super><Shift>a'

    # Voice edit hotkey
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voice-edit/ name 'Agent-CLI Voice Edit'
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voice-edit/ command "$VOICE_EDIT_SCRIPT"
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voice-edit/ binding '<Super><Shift>v'

    echo "✅ Added hotkeys to GNOME"
}

configure_kde() {
    echo "⚙️ Configuring KDE hotkeys..."
    echo "🔧 KDE hotkeys need to be configured manually through System Settings:"
    echo "   1. Open System Settings → Shortcuts → Custom Shortcuts"
    echo "   2. Click 'Edit' → 'New' → 'Global Shortcut' → 'Command/URL'"
    echo ""
    show_hotkey_bindings "kde"
}

configure_sway() {
    echo "⚙️ Configuring Sway hotkeys..."
    local config_file="$HOME/.config/sway/config"

    if [ ! -f "$config_file" ]; then
        echo "❌ Sway config not found at $config_file"
        echo "Please add these bindings manually to your Sway config:"
        show_hotkey_bindings "sway"
        return
    fi

    # Backup and add bindings
    cp "$config_file" "$config_file.backup.$(date +%s)"

    echo "" >> "$config_file"
    echo "# Agent-CLI hotkeys" >> "$config_file"
    echo "bindsym \$mod+Shift+r exec $TRANSCRIBE_SCRIPT" >> "$config_file"
    echo "bindsym \$mod+Shift+a exec $AUTOCORRECT_SCRIPT" >> "$config_file"
    echo "bindsym \$mod+Shift+v exec $VOICE_EDIT_SCRIPT" >> "$config_file"

    echo "✅ Added hotkeys to Sway config"
    echo "↻ Reload Sway with: swaymsg reload"
}

configure_xfce() {
    echo "⚙️ Configuring XFCE hotkeys..."
    echo "🔧 XFCE hotkeys need to be configured manually:"
    echo "   1. Open Settings Manager → Keyboard → Application Shortcuts"
    echo "   2. Click 'Add' and enter the command and shortcut"
    echo ""
    show_hotkey_bindings "xfce"
}

configure_i3() {
    echo "⚙️ Configuring i3 hotkeys..."
    local config_file="$HOME/.config/i3/config"

    if [ ! -f "$config_file" ]; then
        echo "❌ i3 config not found at $config_file"
        echo "Please add these bindings manually to your i3 config:"
        show_hotkey_bindings "i3"
        return
    fi

    # Backup and add bindings
    cp "$config_file" "$config_file.backup.$(date +%s)"

    echo "" >> "$config_file"
    echo "# Agent-CLI hotkeys" >> "$config_file"
    echo "bindsym \$mod+Shift+r exec --no-startup-id $TRANSCRIBE_SCRIPT" >> "$config_file"
    echo "bindsym \$mod+Shift+a exec --no-startup-id $AUTOCORRECT_SCRIPT" >> "$config_file"
    echo "bindsym \$mod+Shift+v exec --no-startup-id $VOICE_EDIT_SCRIPT" >> "$config_file"

    echo "✅ Added hotkeys to i3 config"
    echo "↻ Reload i3 with: i3-msg reload"
}

configure_generic() {
    echo "⚙️ Setting up generic hotkeys using xbindkeys..."

    # Check if xbindkeys is available
    if ! command -v xbindkeys &> /dev/null; then
        echo "📦 Installing xbindkeys..."
        if command -v apt &> /dev/null; then
            sudo apt install xbindkeys
        elif command -v dnf &> /dev/null; then
            sudo dnf install xbindkeys
        elif command -v pacman &> /dev/null; then
            sudo pacman -S xbindkeys
        else
            echo "❌ Please install xbindkeys manually"
            show_hotkey_bindings "manual"
            return
        fi
    fi

    # Create xbindkeys config
    local xbindkeys_config="$HOME/.xbindkeysrc"

    # Backup existing config
    [ -f "$xbindkeys_config" ] && cp "$xbindkeys_config" "$xbindkeys_config.backup.$(date +%s)"

    # Add Agent-CLI bindings
    cat >> "$xbindkeys_config" << EOF

# Agent-CLI hotkeys
"$TRANSCRIBE_SCRIPT"
    control+shift + r

"$AUTOCORRECT_SCRIPT"
    control+shift + a

"$VOICE_EDIT_SCRIPT"
    control+shift + v
EOF

    echo "✅ Added hotkeys to xbindkeys config"
    echo "🚀 Starting xbindkeys..."
    pkill xbindkeys 2>/dev/null || true
    xbindkeys

    # Add to autostart
    if [ ! -f "$HOME/.config/autostart/xbindkeys.desktop" ]; then
        mkdir -p "$HOME/.config/autostart"
        cat > "$HOME/.config/autostart/xbindkeys.desktop" << EOF
[Desktop Entry]
Type=Application
Exec=xbindkeys
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=xbindkeys
EOF
        echo "✅ Added xbindkeys to autostart"
    fi
}

show_hotkey_bindings() {
    local format="$1"
    echo "Manual hotkey configuration needed:"
    echo ""
    case "$format" in
        "hyprland"|"sway")
            echo "Super+Shift+R → $TRANSCRIBE_SCRIPT"
            echo "Super+Shift+A → $AUTOCORRECT_SCRIPT"
            echo "Super+Shift+V → $VOICE_EDIT_SCRIPT"
            ;;
        "i3")
            echo "\$mod+Shift+R → $TRANSCRIBE_SCRIPT"
            echo "\$mod+Shift+A → $AUTOCORRECT_SCRIPT"
            echo "\$mod+Shift+V → $VOICE_EDIT_SCRIPT"
            ;;
        *)
            echo "Ctrl+Shift+R → $TRANSCRIBE_SCRIPT"
            echo "Ctrl+Shift+A → $AUTOCORRECT_SCRIPT"
            echo "Ctrl+Shift+V → $VOICE_EDIT_SCRIPT"
            ;;
    esac
}

# Main execution
setup_notifications

DESKTOP=$(detect_desktop)
configure_hotkeys "$DESKTOP"

echo ""
echo "✅ Setup complete! Hotkeys configured:"
echo "  Transcribe: Super+Shift+R (or Ctrl+Shift+R)"
echo "  Autocorrect: Super+Shift+A (or Ctrl+Shift+A)"
echo "  Voice Edit: Super+Shift+V (or Ctrl+Shift+V)"
echo ""
echo "If hotkeys don't work, check your desktop environment's"
echo "keyboard shortcut settings for conflicts."
