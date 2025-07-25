#!/usr/bin/env bash

# Toggle script for agent-cli transcription on macOS

if pgrep -f "agent-cli transcribe" > /dev/null; then
    pkill -INT -f "agent-cli transcribe"
    /opt/homebrew/bin/terminal-notifier -title "🛑 Stopped" -message "Processing results..."
else
    /opt/homebrew/bin/terminal-notifier -title "🎙️ Started" -message "Listening..."
    (
        OUTPUT=$("$HOME/.local/bin/agent-cli" transcribe --llm --quiet 2>/dev/null)
        if [ -n "$OUTPUT" ]; then
            /opt/homebrew/bin/terminal-notifier -title "📄 Result" -message "$OUTPUT"
        else
            /opt/homebrew/bin/terminal-notifier -title "❌ Error" -message "No output"
        fi
    ) &
fi
