#!/usr/bin/env bash

# Toggle script for agent-cli autocorrect on macOS

/opt/homebrew/bin/terminal-notifier -title "📝 Autocorrect" -message "Processing clipboard text..."

OUTPUT=$("$HOME/.local/bin/agent-cli" autocorrect --quiet 2>/dev/null)
if [ -n "$OUTPUT" ]; then
    /opt/homebrew/bin/terminal-notifier -title "✅ Corrected" -message "$OUTPUT"
else
    /opt/homebrew/bin/terminal-notifier -title "❌ Error" -message "No text to correct"
fi
