#!/usr/bin/env bash

# Toggle script for agent-cli transcription on macOS

set -euo pipefail

NOTIFIER=${NOTIFIER:-/opt/homebrew/bin/terminal-notifier}
CLI_BIN=${CLI_BIN:-"$HOME/.local/bin/agent-cli"}
TRANSCRIBE_MATCH="agent-cli transcribe"
RECORDING_GROUP="agent-cli-transcribe-recording"
TEMP_PREFIX="agent-cli-transcribe-temp"
WAIT_AFTER_INT_TICKS=${WAIT_AFTER_INT_TICKS:-60}   # 6 seconds max
WAIT_AFTER_TERM_TICKS=${WAIT_AFTER_TERM_TICKS:-30} # 3 seconds max
WAIT_AFTER_KILL_TICKS=${WAIT_AFTER_KILL_TICKS:-10} # 1 second max
LAST_STOP_SIGNAL=""

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

notify_temp() {
    local title=$1
    local message=$2
    local duration=${3:-4}  # 4 seconds default
    local group="${TEMP_PREFIX}-${RANDOM}-$$"

    "$NOTIFIER" -title "$title" -message "$message" -group "$group" >/dev/null 2>&1 || true
    (
        sleep "$duration"
        "$NOTIFIER" -remove "$group" >/dev/null 2>&1 || true
    ) &
}

if transcribe_running; then
    if stop_transcription; then
        "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
        if [[ "$LAST_STOP_SIGNAL" == "INT" ]]; then
            notify_temp "🛑 Stopped" "Processing results..."
        else
            notify_temp "⛔ Forced Stop" "Transcription was unresponsive; forced exit."
        fi
    else
        "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
        notify_temp "❌ Error" "Could not stop transcription. Check running processes."
    fi
else
    if [[ ! -x "$CLI_BIN" ]]; then
        notify_temp "❌ Error" "agent-cli not found at $CLI_BIN"
        exit 1
    fi

    "$NOTIFIER" -title "🎙️ Started" -message "Listening..." -group "$RECORDING_GROUP" >/dev/null 2>&1 || true
    (
        OUTPUT=$("$CLI_BIN" transcribe --llm --quiet 2>/dev/null)
        "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
        if [ -n "$OUTPUT" ]; then
            notify_temp "📄 Result" "$OUTPUT"
        else
            notify_temp "❌ Error" "No output"
        fi
    ) &
fi
