#!/usr/bin/env bash

# Toggle script for agent-cli transcription on macOS
# Shows a subtle menu bar icon while recording instead of notification banners.

NOTIFIER=${NOTIFIER:-/opt/homebrew/bin/terminal-notifier}
AGENT_CLI=${AGENT_CLI:-"$HOME/.local/bin/agent-cli"}
PID_FILE=${PID_FILE:-"$HOME/.cache/agent-cli/transcribe.pid"}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MENUBAR_ICON="$SCRIPT_DIR/menubar-icon"
MENUBAR_PID_FILE="$HOME/.cache/agent-cli/menubar-icon.pid"
TEMP_PREFIX="agent-cli-transcribe-temp"

notify_temp() {
    local title=$1
    local message=$2
    local duration=${3:-4}
    local group="${TEMP_PREFIX}-${RANDOM}-$$"

    "$NOTIFIER" -title "$title" -message "$message" -group "$group"
    (
        sleep "$duration"
        "$NOTIFIER" -remove "$group" >/dev/null 2>&1 || true
    ) &
}

show_menubar_icon() {
    # Compile on first use if binary doesn't exist
    if [ ! -x "$MENUBAR_ICON" ] && [ -f "$MENUBAR_ICON.swift" ]; then
        swiftc -O "$MENUBAR_ICON.swift" -o "$MENUBAR_ICON" 2>/dev/null
    fi
    if [ -x "$MENUBAR_ICON" ]; then
        "$MENUBAR_ICON" "🎙️" "agent-cli: recording" &
        echo $! > "$MENUBAR_PID_FILE"
    fi
}

hide_menubar_icon() {
    # Kill by PID file
    if [ -f "$MENUBAR_PID_FILE" ]; then
        local pid
        pid=$(cat "$MENUBAR_PID_FILE" 2>/dev/null || true)
        if [ -n "$pid" ]; then
            kill "$pid" >/dev/null 2>&1 || true
        fi
        rm -f "$MENUBAR_PID_FILE"
    fi
    # Fallback: kill any remaining instances
    pkill -x menubar-icon >/dev/null 2>&1 || true
}

is_transcribe_running() {
    [ -f "$PID_FILE" ] || return 1
    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null || true)
    [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1
}

if is_transcribe_running; then
    "$AGENT_CLI" transcribe --toggle --quiet >/dev/null 2>&1 || true
    hide_menubar_icon
    notify_temp "🛑 Stopped" "Processing results..."
else
    # Clean up any stale icon from a previous run
    hide_menubar_icon
    show_menubar_icon
    (
        OUTPUT=$("$AGENT_CLI" transcribe --toggle --llm --quiet 2>/dev/null)
        hide_menubar_icon
        if [ -n "$OUTPUT" ]; then
            notify_temp "📄 Result" "$OUTPUT"
        else
            notify_temp "❌ Error" "No output"
        fi
    ) &
fi
