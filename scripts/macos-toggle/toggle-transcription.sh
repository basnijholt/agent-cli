#!/usr/bin/env bash

# Toggle script for agent-cli transcription on macOS

# Function to send notification
notify() {
    local title="$1"
    local message="$2"
    terminal-notifier -title "$title" -message "$message"
}

# Check if agent-cli transcribe is already running
if pgrep -f "agent-cli transcribe" > /dev/null; then
    # Transcription is running - stop it
    pkill -INT -f "agent-cli transcribe"
    notify "🛑 Transcription Stopped" "Processing results..."
else
    # Transcription is not running - start it

    # Use agent-cli from standard uv tool install location
    AGENT_CLI="$HOME/.local/bin/agent-cli"

    # Notify user that recording has started
    notify "🎙️ Transcription Started" "Listening in background..."

    # Start transcription in background
    (
        OUTPUT=$("$AGENT_CLI" transcribe --llm --quiet 2>/dev/null)
        exit_code=$?

        if [ $exit_code -eq 0 ] && [ -n "$OUTPUT" ]; then
            # Success - show result (already copied to clipboard by agent-cli)
            notify "📄 Transcription Result" "$OUTPUT"
        elif [ $exit_code -eq 130 ]; then
            # Interrupted with Ctrl+C (SIGINT) - this is expected
            notify "🛑 Transcription Cancelled" "Stopped by user"
        else
            # Error occurred
            notify "❌ Transcription Error" "Check agent-cli setup and services"
        fi
    ) &
fi
