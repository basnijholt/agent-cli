#!/usr/bin/env bash

# Check if zellij is installed
if ! command -v zellij &> /dev/null; then
    echo "📺 Zellij not found. Installing..."
    uvx dotbins get zellij-org/zellij
    export PATH="$HOME/.local/bin:$PATH"
fi

# Get the current directory
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"

# Help text for zellij panes
HELP_TEXT='╔═══════════════════════════════════════════════════════════════════╗
║                    Agent CLI Services                             ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  🔴 IMPORTANT:                                                    ║
║  • Ctrl-O d  → Detach (keeps services running in background!)     ║
║  • Ctrl-Q    → Quit (STOPS all services!)                         ║
║                                                                   ║
║  To reattach later: $ zellij attach agent-cli                     ║
║                                                                   ║
╠═══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║  Services Running:                                                ║
║  • Ollama (LLM) - Port 11434                                      ║
║  • Whisper (STT) - Port 10300                                     ║
║  • Piper (TTS) - Port 10200                                       ║
║  • OpenWakeWord - Port 10400                                      ║
║                                                                   ║
║  Navigation:                                                      ║
║  • Alt + ← → ↑ ↓  - Move between panes                            ║
║  • Ctrl-F         - Toggle this help                              ║
║  • q              - Close this help                               ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝'

# On macOS, check if services are running via brew/launchd
OLLAMA_BREW_SERVICE=false
WHISPER_LAUNCHD=false
TTS_LAUNCHD=false
if [ "$(uname -s)" = "Darwin" ]; then
    # Check if Ollama is running as a brew service
    if launchctl list homebrew.mxcl.ollama &>/dev/null; then
        OLLAMA_BREW_SERVICE=true
    fi
    # Check if Whisper is running as an agent-cli daemon
    if launchctl list com.agent_cli.whisper &>/dev/null; then
        WHISPER_LAUNCHD=true
    fi
    # Check if TTS is running as an agent-cli daemon (tts-kokoro or tts-piper)
    if launchctl list com.agent_cli.tts &>/dev/null; then
        TTS_LAUNCHD=true
    fi
fi

# Create .runtime directory
mkdir -p "$SCRIPTS_DIR/.runtime"

# Generate Ollama pane based on whether brew service is running
if [ "$OLLAMA_BREW_SERVICE" = true ]; then
    OLLAMA_PANE="            pane {
                name \"Ollama (brew service)\"
                command \"sh\"
                args \"-c\" \"echo '🧠 Ollama is running as a brew background service'; echo ''; echo 'To view status:'; echo '  brew services info ollama'; echo ''; echo 'To stop:'; echo '  brew services stop ollama'; echo ''; echo 'To restart:'; echo '  brew services restart ollama'; echo ''; read -r\"
            }"
else
    OLLAMA_PANE="            pane {
                name \"Ollama\"
                command \"ollama\"
                args \"serve\"
            }"
fi

# Generate Whisper pane command based on whether launchd service is running
if [ "$WHISPER_LAUNCHD" = true ]; then
    WHISPER_PANE="            pane {
                name \"Whisper (launchd)\"
                command \"sh\"
                args \"-c\" \"echo '🎤 Whisper is running as a background launchd service'; echo ''; echo 'Service: com.agent_cli.whisper'; echo 'Logs: ~/Library/Logs/agent-cli-whisper/'; echo ''; echo 'To view logs:'; echo '  tail -f ~/Library/Logs/agent-cli-whisper/whisper.out'; echo ''; echo 'To uninstall:'; echo '  agent-cli daemon uninstall whisper'; echo ''; read -r\"
            }"
else
    WHISPER_PANE="            pane {
                name \"Whisper\"
                command \"agent-cli\"
                args \"server\" \"whisper\"
            }"
fi

# Generate TTS pane based on whether launchd service is running
if [ "$TTS_LAUNCHD" = true ]; then
    TTS_PANE="                pane {
                    name \"TTS (launchd)\"
                    command \"sh\"
                    args \"-c\" \"echo '🔊 TTS is running as a background launchd service'; echo ''; echo 'Service: com.agent_cli.tts'; echo 'Logs: ~/Library/Logs/agent-cli-tts/'; echo ''; echo 'To view logs:'; echo '  tail -f ~/Library/Logs/agent-cli-tts/tts.out'; echo ''; echo 'To uninstall:'; echo '  agent-cli daemon uninstall tts-kokoro  # or tts-piper'; echo ''; read -r\"
                }"
else
    TTS_PANE="                pane {
                    name \"TTS\"
                    command \"agent-cli\"
                    args \"server\" \"tts\" \"--backend\" \"piper\"
                }"
fi

BOTTOM_PANES="        pane split_direction=\"horizontal\" {
$WHISPER_PANE
            pane split_direction=\"horizontal\" {
$TTS_PANE
                pane {
                    name \"OpenWakeWord\"
                    cwd \"$SCRIPTS_DIR\"
                    command \"./run-openwakeword.sh\"
                }
            }
        }"

TOP_PANES="        pane split_direction=\"horizontal\" {
$OLLAMA_PANE
            pane {
                name \"Help\"
                command \"sh\"
                args \"-c\" \"echo '$HELP_TEXT' | less\"
            }
        }"

cat > "$SCRIPTS_DIR/.runtime/agent-cli-layout.kdl" << EOF
session_name "agent-cli"

layout {
    pane split_direction="vertical" {
$TOP_PANES
$BOTTOM_PANES
    }

    floating_panes {
        pane {
            name "Help"
            x "10%"
            y "10%"
            width "80%"
            height "80%"
            command "sh"
            close_on_exit true
            args "-c" "echo '$HELP_TEXT' | less"
        }
    }
}
EOF

# Function to show common usage instructions
show_usage() {
    echo "❌ Use 'Ctrl-Q' to quit Zellij"
    echo "🔌 Use 'Ctrl-O d' to detach from the session"
    echo "🔗 Use 'zellij attach agent-cli' to reattach"
}

# Function to start a new Zellij session
start_new_session() {
    if [ "$AGENT_CLI_NO_ATTACH" = "true" ]; then
        # Start detached
        zellij --session agent-cli --layout "$SCRIPTS_DIR/.runtime/agent-cli-layout.kdl" &
        sleep 1  # Give it a moment to start
        echo "✅ Session 'agent-cli' started in background. Use 'zellij attach agent-cli' to view."
    else
        show_usage
        # Start zellij with layout file - session name is specified in the layout
        zellij --layout "$SCRIPTS_DIR/.runtime/agent-cli-layout.kdl"
    fi
}

# Check if agent-cli session already exists and is running
# Case 1: Session exists but has exited - clean it up and start fresh
if zellij list-sessions 2>/dev/null | grep "agent-cli" | grep -q "EXITED"; then
    echo "🧹 Found exited session 'agent-cli'. Cleaning up..."
    zellij delete-session agent-cli
    echo "🆕 Starting fresh services in Zellij..."
    start_new_session
# Case 2: Session exists and is running - attach to it if requested
elif zellij list-sessions 2>/dev/null | grep -q "agent-cli"; then
    if [ "$AGENT_CLI_NO_ATTACH" = "true" ]; then
        echo "✅ Session 'agent-cli' is already running. Not attaching as requested."
    else
        echo "🔗 Session 'agent-cli' already exists and is running. Attaching..."
        show_usage
        zellij attach agent-cli
    fi
# Case 3: No session exists - create a new one
else
    echo "🚀 Starting all services in Zellij..."
    start_new_session
fi
