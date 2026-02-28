#!/usr/bin/env bash

# Toggle script for agent-cli transcription on macOS

NOTIFIER=${NOTIFIER:-/opt/homebrew/bin/terminal-notifier}
AGENT_CLI=${AGENT_CLI:-"$HOME/.local/bin/agent-cli"}
PID_FILE=${PID_FILE:-"$HOME/.cache/agent-cli/transcribe.pid"}
RECORDING_GROUP="agent-cli-transcribe-recording"
TEMP_PREFIX="agent-cli-transcribe-temp"

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

is_transcribe_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
            return 0
        fi
    fi

    # Fallback for legacy/orphaned processes from older versions.
    pgrep -f "agent-cli-transcribe" >/dev/null 2>&1
}

if is_transcribe_running; then
    if [ -f "$PID_FILE" ]; then
        "$AGENT_CLI" transcribe --toggle --quiet >/dev/null 2>&1 || true
    else
        # Legacy fallback when no PID file exists but process title matches.
        pkill -INT -f "agent-cli-transcribe" >/dev/null 2>&1 || true
    fi

    "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
    notify_temp "🛑 Stopped" "Processing results..."
else
    "$NOTIFIER" -title "🎙️ Started" -message "Listening..." -group "$RECORDING_GROUP"
    (
        OUTPUT=$("$AGENT_CLI" transcribe --toggle --llm --quiet 2>/dev/null)
        "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
        if [ -n "$OUTPUT" ]; then
            notify_temp "📄 Result" "$OUTPUT"
        else
            notify_temp "❌ Error" "No output"
        fi
    ) &
fi
