#!/bin/bash

# Check if zellij is installed
if ! command -v zellij &> /dev/null; then
    echo "Zellij not found. Installing..."

    # Detect OS and install accordingly
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install zellij
        else
            echo "Homebrew not found. Please install Homebrew or run the setup script first."
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux - try different methods
        if command -v cargo &> /dev/null; then
            echo "Installing zellij via cargo..."
            cargo install zellij
        else
            echo "Installing zellij binary..."
            mkdir -p ~/.local/bin
            curl -L https://github.com/zellij-org/zellij/releases/latest/download/zellij-x86_64-unknown-linux-musl.tar.gz | tar -xz -C ~/.local/bin/
            chmod +x ~/.local/bin/zellij
            export PATH="$HOME/.local/bin:$PATH"
        fi
    else
        echo "Unsupported OS. Please install zellij manually."
        exit 1
    fi
fi

# Get the current directory
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"


# Create .runtime directory and Zellij layout file
mkdir -p "$SCRIPTS_DIR/.runtime"
cat > "$SCRIPTS_DIR/.runtime/agent-cli-layout.kdl" << EOF
session_name "agent-cli"

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
                command "./run-whisper.sh"
            }
            pane split_direction="horizontal" {
                pane {
                    name "Piper"
                    cwd "$SCRIPTS_DIR"
                    command "./run-piper.sh"
                }
                pane {
                    name "OpenWakeWord"
                    cwd "$SCRIPTS_DIR"
                    command "./run-openwakeword.sh"
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
    # Start zellij with layout file - session name is specified in the layout
    zellij --layout "$SCRIPTS_DIR/.runtime/agent-cli-layout.kdl"
fi
