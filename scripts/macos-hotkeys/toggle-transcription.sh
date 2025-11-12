#!/usr/bin/env bash

# Toggle script for agent-cli transcription on macOS

NOTIFIER=${NOTIFIER:-/opt/homebrew/bin/terminal-notifier}
RECORDING_GROUP="agent-cli-transcribe-recording"
STATUS_GROUP="agent-cli-transcribe-status"
RESULT_GROUP="agent-cli-transcribe-result"

notify() {
    local title=$1
    local message=$2
    shift 2
    "$NOTIFIER" -title "$title" -message "$message" "$@"
}

notify_temp() {
    local title=$1
    local message=$2
    local group=$3
    local duration=${4:-5}

    "$NOTIFIER" -remove "$group" >/dev/null 2>&1 || true
    notify "$title" "$message" -group "$group"
    (
        sleep "$duration"
        "$NOTIFIER" -remove "$group" >/dev/null 2>&1 || true
    ) &
}

if pgrep -f "agent-cli transcribe" > /dev/null; then
    pkill -INT -f "agent-cli transcribe"
    "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
    notify_temp "🛑 Stopped" "Processing results..." "$STATUS_GROUP" 4
else
    notify "🎙️ Started" "Listening..." -group "$RECORDING_GROUP"
    (
        OUTPUT=$("$HOME/.local/bin/agent-cli" transcribe --llm --quiet 2>/dev/null)
        "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
        if [ -n "$OUTPUT" ]; then
            notify_temp "📄 Result" "$OUTPUT" "$RESULT_GROUP" 4
        else
            notify_temp "❌ Error" "No output" "$RESULT_GROUP" 4
        fi
    ) &
fi
