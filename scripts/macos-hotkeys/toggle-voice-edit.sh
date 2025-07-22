#!/usr/bin/env bash

# Toggle script for agent-cli voice-edit on macOS

if pgrep -f "agent-cli voice-edit" > /dev/null; then
    pkill -INT -f "agent-cli voice-edit"
    /opt/homebrew/bin/terminal-notifier -title "🛑 Stopped" -message "Processing voice command..."
else
    /opt/homebrew/bin/terminal-notifier -title "🎙️ Started" -message "Listening for voice command..."
    (
        OUTPUT=$("$HOME/.local/bin/agent-cli" voice-edit --quiet 2>/dev/null)
        if [ -n "$OUTPUT" ]; then
            /opt/homebrew/bin/terminal-notifier -title "✨ Voice Edit Result" -message "$OUTPUT"
        else
            /opt/homebrew/bin/terminal-notifier -title "❌ Error" -message "No output"
        fi
    ) &
fi
