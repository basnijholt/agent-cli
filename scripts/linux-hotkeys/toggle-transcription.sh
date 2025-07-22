#!/usr/bin/env bash

# Toggle script for agent-cli transcription on Linux
#
# This script provides a simple toggle mechanism for voice transcription:
# - First invocation: Starts transcription in the background
# - Second invocation: Stops transcription and displays the result
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

# Check if agent-cli transcribe is already running
if pgrep -f "agent-cli transcribe" > /dev/null; then
    # Transcription is running - stop it
    pkill -INT -f "agent-cli transcribe"
    notify "🛑 Transcription Stopped" "Processing results..."
else
    # Transcription is not running - start it

    # Ensure agent-cli is in PATH
    export PATH="$PATH:$HOME/.local/bin"

    # Notify user that recording has started
    notify "🎙️ Transcription Started" "Listening in background..."

    # Start transcription in background
    (
        OUTPUT=$(agent-cli transcribe --llm --quiet 2>/dev/null)
        if [ -n "$OUTPUT" ]; then
            # Sync clipboard to primary selection (Wayland)
            sync_clipboard
            notify "📄 Transcription Result" "$OUTPUT" 5000
        else
            notify "❌ Error" "No output" 3000
        fi
    ) &
fi
