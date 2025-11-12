#!/usr/bin/env bash

# Toggle script for agent-cli transcription on macOS

NOTIFIER=${NOTIFIER:-/opt/homebrew/bin/terminal-notifier}
RECORDING_GROUP="agent-cli-transcribe-recording"
TEMP_PREFIX="agent-cli-transcribe-temp"

notify_temp() {
    local title=$1
    local message=$2
    local duration=${3:-5}
    local group="${TEMP_PREFIX}-${RANDOM}-$$"

    "$NOTIFIER" -title "$title" -message "$message" -group "$group"
    (
        sleep "$duration"
        "$NOTIFIER" -remove "$group" >/dev/null 2>&1 || true
    ) &
}

if pgrep -f "agent-cli transcribe" > /dev/null; then
    pkill -INT -f "agent-cli transcribe"
    "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
    notify_temp "🛑 Stopped" "Processing results..." 4
else
    "$NOTIFIER" -title "🎙️ Started" -message "Listening..." -group "$RECORDING_GROUP"
    (
        OUTPUT=$("$HOME/.local/bin/agent-cli" transcribe --llm --quiet 2>/dev/null)
        "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
        if [ -n "$OUTPUT" ]; then
            notify_temp "📄 Result" "$OUTPUT" 4
        else
            notify_temp "❌ Error" "No output" 4
        fi
    ) &
fi
