#!/bin/bash

# Check if zellij is installed
if ! command -v zellij &> /dev/null; then
    echo "Installing zellij..."
    brew install zellij
fi

# Get the current directory
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"


# Create a Zellij layout file
cat > agent-cli-layout.kdl << EOF
layout {
    pane split_direction="vertical" {
        pane {
            name "Ollama"
            command "ollama"
            args "serve"
        }
        pane split_direction="horizontal" {
            pane {
                name "Whisper"
                cwd "$SCRIPTS_DIR"
                command "./run-whisper-uvx.sh"
            }
            pane split_direction="horizontal" {
                pane {
                    name "Piper"
                    cwd "$SCRIPTS_DIR"
                    command "./run-piper-uvx.sh"
                }
                pane {
                    name "OpenWakeWord"
                    cwd "$SCRIPTS_DIR"
                    command "./run-openwakeword-uvx.sh"
                }
            }
        }
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
            args "-c" "echo '╔═══════════════════════════════════════════════════════════════════╗
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
╚═══════════════════════════════════════════════════════════════════╝' | less"
        }
    }
}
EOF

# Check if agent-cli session already exists
if zellij list-sessions 2>/dev/null | grep -q "agent-cli"; then
    echo "Session 'agent-cli' already exists. Attaching..."
    echo "Use 'Ctrl-O d' to detach from the session"
    echo "Use 'Ctrl-Q' to quit Zellij"
    zellij attach agent-cli
else
    echo "Starting all services in Zellij..."
    echo "Use 'Ctrl-Q' to quit Zellij"
    echo "Use 'Ctrl-O d' to detach from the session"
    echo "Use 'zellij attach agent-cli' to reattach"
    zellij -n agent-cli --layout agent-cli-layout.kdl
fi
