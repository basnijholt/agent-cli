#!/usr/bin/env bash

# Toggle script for agent-cli voice-edit on macOS

NOTIFIER=${NOTIFIER:-/opt/homebrew/bin/terminal-notifier}
RECORDING_GROUP="agent-cli-voice-edit-recording"
TEMP_PREFIX="agent-cli-voice-edit-temp"

notify_temp() {
    local title=$1
    local message=$2
    local duration=${3:-4}  # 4 seconds default
    local group="${TEMP_PREFIX}-${RANDOM}-$$"

    "$NOTIFIER" -title "$title" -message "$message" -group "$group"
    (
        sleep "$duration"
        "$NOTIFIER" -remove "$group" >/dev/null 2>&1 || true
    ) &
}

if pgrep -f "agent-cli voice-edit" > /dev/null; then
    pkill -INT -f "agent-cli voice-edit"
    "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
    notify_temp "🛑 Stopped" "Processing voice command..."
else
    "$NOTIFIER" -title "🎙️ Started" -message "Listening for voice command..." -group "$RECORDING_GROUP"
    (
        OUTPUT=$("$HOME/.local/bin/agent-cli" voice-edit --quiet 2>/dev/null)
        "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
        if [ -n "$OUTPUT" ]; then
            notify_temp "✨ Voice Edit Result" "$OUTPUT"
        else
            notify_temp "❌ Error" "No output"
        fi
    ) &
fi
