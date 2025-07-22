#!/usr/bin/env bash

# Toggle script for agent-cli voice-edit on Linux
#
# This script provides voice editing for clipboard text:
# - First invocation: Starts voice editing in the background
# - Second invocation: Stops voice editing and displays the result
#
# Works across different Linux desktop environments

# Function to send notification
notify() {
    local title="$1"
    local message="$2"
    local timeout="${3:-3000}"

    if command -v notify-send &> /dev/null; then
        notify-send -t "$timeout" "$title" "$message"
    elif command -v dunstify &> /dev/null; then
        dunstify -t "$timeout" "$title" "$message"
    else
        echo "$title: $message"
    fi
}

# Function to sync clipboard (Wayland)
sync_clipboard() {
    if command -v wl-paste &> /dev/null && command -v wl-copy &> /dev/null; then
        wl-paste | wl-copy -p 2>/dev/null || true
    fi
}

# Check if agent-cli voice-edit is already running
if pgrep -f "agent-cli voice-edit" > /dev/null; then
    # Voice edit is running - stop it
    pkill -INT -f "agent-cli voice-edit"
    notify "🛑 Voice Edit Stopped" "Processing voice command..."
else
    # Voice edit is not running - start it

    # Ensure agent-cli is in PATH
    export PATH="$PATH:$HOME/.local/bin"

    # Notify user that recording has started
    notify "🎙️ Voice Edit Started" "Listening for voice command..."

    # Start voice edit in background
    (
        OUTPUT=$(agent-cli voice-edit --quiet 2>/dev/null)
        if [ -n "$OUTPUT" ]; then
            # Sync clipboard to primary selection (Wayland)
            sync_clipboard
            notify "✨ Voice Edit Result" "$OUTPUT" 5000
        else
            notify "❌ Error" "No output" 3000
        fi
    ) &
fi
