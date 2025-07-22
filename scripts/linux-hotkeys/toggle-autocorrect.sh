#!/usr/bin/env bash

# Toggle script for agent-cli autocorrect on Linux
#
# This script corrects text from clipboard using AI:
# - Reads text from clipboard
# - Processes it with LLM for grammar/spelling corrections
# - Displays the corrected result
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

# Ensure agent-cli is in PATH
export PATH="$PATH:$HOME/.local/bin"

notify "📝 Autocorrect" "Processing clipboard text..."

OUTPUT=$(agent-cli autocorrect --quiet 2>/dev/null) && {
    # Sync clipboard to primary selection (Wayland)
    sync_clipboard
    notify "✅ Corrected" "$OUTPUT" 5000
} || {
    notify "❌ Error" "No text to correct or processing failed" 3000
}
