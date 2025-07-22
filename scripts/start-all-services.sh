#!/bin/bash

# Check if zellij is installed
if ! command -v zellij &> /dev/null; then
    echo "Installing zellij..."
    brew install zellij
fi

# Create a Zellij layout file
cat > agent-cli-layout.kdl << 'EOF'
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
                command "./run-whisper-uvx.sh"
            }
            pane split_direction="horizontal" {
                pane {
                    name "Piper"
                    command "./run-piper-uvx.sh"
                }
                pane {
                    name "OpenWakeWord"
                    command "./run-openwakeword-uvx.sh"
                }
            }
        }
    }
}
EOF

# Start Zellij with the layout
echo "Starting all services in Zellij..."
echo "Use 'Ctrl-Q' to quit Zellij"
echo "Use 'Ctrl-O d' to detach from the session"
echo "Use 'zellij attach agent-cli' to reattach"

zellij --session agent-cli --layout agent-cli-layout.kdl
