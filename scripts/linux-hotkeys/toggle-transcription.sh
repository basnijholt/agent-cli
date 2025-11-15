#!/usr/bin/env bash

# Toggle script for agent-cli transcription on Linux
#
# This script provides a simple toggle mechanism for voice transcription:
# - First invocation: Starts transcription in the background
# - Second invocation: Stops transcription and displays the result
#
# Works across different Linux desktop environments

set -euo pipefail

CLI_BIN=${CLI_BIN:-"$HOME/.local/bin/agent-cli"}
TRANSCRIBE_MATCH="agent-cli transcribe"
WAIT_AFTER_INT_TICKS=${WAIT_AFTER_INT_TICKS:-60}
WAIT_AFTER_TERM_TICKS=${WAIT_AFTER_TERM_TICKS:-30}
WAIT_AFTER_KILL_TICKS=${WAIT_AFTER_KILL_TICKS:-10}
LAST_STOP_SIGNAL=""

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

transcribe_running() {
    pgrep -f "$TRANSCRIBE_MATCH" >/dev/null 2>&1
}

wait_for_transcribe_exit() {
    local attempts=$1
    for ((i = 0; i < attempts; i++)); do
        if ! transcribe_running; then
            return 0
        fi
        sleep 0.1
    done
    return 1
}

stop_transcription() {
    LAST_STOP_SIGNAL=""
    if ! transcribe_running; then
        return 0
    fi

    pkill -INT -f "$TRANSCRIBE_MATCH" >/dev/null 2>&1 || true
    if wait_for_transcribe_exit "$WAIT_AFTER_INT_TICKS"; then
        LAST_STOP_SIGNAL="INT"
        return 0
    fi

    pkill -TERM -f "$TRANSCRIBE_MATCH" >/dev/null 2>&1 || true
    if wait_for_transcribe_exit "$WAIT_AFTER_TERM_TICKS"; then
        LAST_STOP_SIGNAL="TERM"
        return 0
    fi

    pkill -KILL -f "$TRANSCRIBE_MATCH" >/dev/null 2>&1 || true
    if wait_for_transcribe_exit "$WAIT_AFTER_KILL_TICKS"; then
        LAST_STOP_SIGNAL="KILL"
        return 0
    fi

    return 1
}

# Check if agent-cli transcribe is already running
if transcribe_running; then
    # Transcription is running - stop it
    if stop_transcription; then
        if [[ "$LAST_STOP_SIGNAL" == "INT" ]]; then
            notify "🛑 Transcription Stopped" "Processing results..."
        else
            notify "⛔ Forced Stop" "Session was unresponsive, forced exit."
        fi
    else
        notify "❌ Error" "Could not stop transcription. See running processes."
    fi
else
    # Transcription is not running - start it

    # Ensure agent-cli is in PATH
    export PATH="$PATH:$HOME/.local/bin"

    if [[ ! -x "$CLI_BIN" ]]; then
        notify "❌ Error" "agent-cli not found at $CLI_BIN"
        exit 1
    fi

    # Notify user that recording has started
    notify "🎙️ Transcription Started" "Listening in background..."

    # Start transcription in background
    (
        OUTPUT=$("$CLI_BIN" transcribe --llm --quiet 2>/dev/null)
        if [ -n "$OUTPUT" ]; then
            # Sync clipboard to primary selection (Wayland)
            sync_clipboard
            notify "📄 Transcription Result" "$OUTPUT" 5000
        else
            notify "❌ Error" "No output" 3000
        fi
    ) &
fi
