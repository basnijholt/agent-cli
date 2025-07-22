#!/usr/bin/env bash

# Toggle script for agent-cli voice-edit on macOS

if pgrep -f "agent-cli voice-edit" > /dev/null; then
    "$HOME/.local/bin/agent-cli" voice-edit --stop --quiet 2>/dev/null
    /opt/homebrew/bin/terminal-notifier -title "🛑 Voice Edit Stopped" -message "Session ended"
else
    /opt/homebrew/bin/terminal-notifier -title "🎙️ Voice Edit Started" -message "Listening for voice commands..."
    "$HOME/.local/bin/agent-cli" voice-edit --quiet 2>/dev/null &
fi
