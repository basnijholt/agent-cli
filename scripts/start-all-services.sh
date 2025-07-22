#!/bin/bash

# Check if zellij is installed
if ! command -v zellij &> /dev/null; then
    echo "Zellij not found. Installing..."
    uvx dotbins get zellij-org/zellij
    export PATH="$HOME/.local/bin:$PATH"
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
            args "-c" "cat $SCRIPTS_DIR/zellij_help.txt | less"
        }
    }
}
EOF

# Function to show common usage instructions
show_usage() {
    echo "Use 'Ctrl-Q' to quit Zellij"
    echo "Use 'Ctrl-O d' to detach from the session"
    echo "Use 'zellij attach agent-cli' to reattach"
}

# Check if agent-cli session already exists and is running
# Case 1: Session exists but has exited - clean it up and start fresh
if zellij list-sessions 2>/dev/null | grep "agent-cli" | grep -q "EXITED"; then
    echo "🧹 Found exited session 'agent-cli'. Cleaning up..."
    zellij delete-session agent-cli
    echo "Starting fresh services in Zellij..."
    show_usage
    # Start zellij with layout file - session name is specified in the layout
    zellij --layout "$SCRIPTS_DIR/.runtime/agent-cli-layout.kdl"
# Case 2: Session exists and is running - attach to it
elif zellij list-sessions 2>/dev/null | grep -q "agent-cli"; then
    echo "🔗 Session 'agent-cli' already exists and is running. Attaching..."
    show_usage
    zellij attach agent-cli
# Case 3: No session exists - create a new one
else
    echo "🚀 Starting all services in Zellij..."
    show_usage
    # Start zellij with layout file - session name is specified in the layout
    zellij --layout "$SCRIPTS_DIR/.runtime/agent-cli-layout.kdl"
fi
