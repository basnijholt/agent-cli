#!/usr/bin/env bash

# Toggle script for agent-cli transcription on macOS

# Function to send notification
notify() {
    local title="$1"
    local message="$2"
    local sound="${3:-default}"
    terminal-notifier -title "$title" -message "$message" -sound "$sound"
}

# Check if agent-cli transcribe is already running
if pgrep -f "agent-cli transcribe" > /dev/null; then
    # Transcription is running - stop it
    pkill -INT -f "agent-cli transcribe"
    notify "🛑 Transcription Stopped" "Processing results..." "Glass"
else
    # Transcription is not running - start it

    # Use the correct agent-cli path (uv tool installation)
    AGENT_CLI="$HOME/.local/bin/agent-cli"
    if [ ! -f "$AGENT_CLI" ]; then
        # Fallback to PATH search
        export PATH="$PATH:$HOME/.local/bin"
        export PATH="$PATH:/opt/homebrew/bin"  # For Homebrew on Apple Silicon
        export PATH="$PATH:/usr/local/bin"     # For Homebrew on Intel
        AGENT_CLI="agent-cli"
    fi

    # Check if agent-cli is available
    if ! command -v "$AGENT_CLI" &> /dev/null; then
        notify "❌ Error" "agent-cli not found: $AGENT_CLI" "Basso"
        exit 1
    fi

    # Notify user that recording has started
    notify "🎙️ Transcription Started" "Listening in background..." "Ping"

    # Start transcription in background
    (
        OUTPUT=$("$AGENT_CLI" transcribe --llm --quiet 2>/dev/null)
        exit_code=$?

        if [ $exit_code -eq 0 ] && [ -n "$OUTPUT" ]; then
            # Success - copy to clipboard and show result
            echo "$OUTPUT" | pbcopy
            notify "📄 Transcription Result" "$OUTPUT" "Hero"
        elif [ $exit_code -eq 130 ]; then
            # Interrupted with Ctrl+C (SIGINT) - this is expected
            notify "🛑 Transcription Cancelled" "Stopped by user" "Glass"
        else
            # Error occurred
            notify "❌ Transcription Error" "Check agent-cli setup and services" "Basso"
        fi
    ) &
fi
