#!/usr/bin/env bash

# Toggle script for agent-cli transcription on macOS

NOTIFIER=${NOTIFIER:-/opt/homebrew/bin/terminal-notifier}
AGENT_CLI=${AGENT_CLI:-"$HOME/.local/bin/agent-cli"}
CACHE_DIR=${CACHE_DIR:-"$HOME/.cache/agent-cli"}
LAST_FILE=${LAST_FILE:-"$CACHE_DIR/transcribe-hotkey.last"}
LOG_FILE=${LOG_FILE:-"$CACHE_DIR/transcribe-hotkey.log"}
AGENT_LOG_FILE=${AGENT_LOG_FILE:-"$CACHE_DIR/transcribe-hotkey-agent.log"}
DEBOUNCE_SECONDS=${DEBOUNCE_SECONDS:-1}
RECORDING_GROUP="agent-cli-transcribe-recording"
TEMP_PREFIX="agent-cli-transcribe-temp"

mkdir -p "$CACHE_DIR"

log_event() {
    printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >> "$LOG_FILE"
}

notify_temp() {
    local title=$1
    local message=$2
    local duration=${3:-4}  # 4 seconds default
    local group="${TEMP_PREFIX}-${RANDOM}-$$"

    "$NOTIFIER" -title "$title" -message "$message" -group "$group" || true
    (
        sleep "$duration"
        "$NOTIFIER" -remove "$group" >/dev/null 2>&1 || true
    ) &
}

is_transcribe_running() {
    local status_json
    if ! status_json=$("$AGENT_CLI" transcribe --status --json 2>> "$LOG_FILE"); then
        log_event "status check failed"
        return 1
    fi
    log_event "status: $status_json"
    printf '%s\n' "$status_json" | grep -Eq '"running"[[:space:]]*:[[:space:]]*true'
}

now=$(date +%s)
last=$(cat "$LAST_FILE" 2>/dev/null || echo 0)

# skhd can emit repeated key-down events while the hotkey chord is held.
# Ignore immediate repeats so one press cannot start and stop recording.
if [ "$((now - last))" -lt "$DEBOUNCE_SECONDS" ]; then
    log_event "ignored repeat hotkey"
    exit 0
fi

echo "$now" > "$LAST_FILE"
log_event "hotkey pressed"

if is_transcribe_running; then
    "$AGENT_CLI" transcribe --stop --quiet --wait-for-start --log-file "$AGENT_LOG_FILE" >> "$LOG_FILE" 2>&1 || true

    "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
    notify_temp "🛑 Stopped" "Processing results..."
    log_event "stop requested"
else
    "$NOTIFIER" -title "🎙️ Recording" -message "Press Cmd+Shift+R again to stop." -group "$RECORDING_GROUP" || true
    (
        OUTPUT=$("$AGENT_CLI" transcribe --start --llm --quiet --log-file "$AGENT_LOG_FILE" 2>> "$LOG_FILE")
        status=$?
        "$NOTIFIER" -remove "$RECORDING_GROUP" >/dev/null 2>&1 || true
        if [ "$status" -ne 0 ]; then
            notify_temp "❌ Error" "Transcription failed. See $AGENT_LOG_FILE"
        elif [ -n "$OUTPUT" ]; then
            notify_temp "📄 Result" "$OUTPUT"
        else
            notify_temp "⚠️ No Transcript" "Recording captured no speech."
        fi
        log_event "recording finished with status $status"
    ) &
    log_event "recording started"
fi
