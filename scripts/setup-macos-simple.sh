#!/bin/bash

set -e

echo "Setting up agent-cli services on macOS (simple version using uvx)..."

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Homebrew is not installed. Please install Homebrew first:"
    echo "/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    brew install uv
fi

# Install Ollama
echo "Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "Please download and install Ollama from https://ollama.com/download"
    echo "Ollama requires macOS 12 Monterey or later"
    echo "After installation, run 'ollama serve' to start the server"
    read -p "Press Enter when Ollama is installed..."
else
    echo "Ollama is already installed"
fi

# Create run scripts using uvx
echo "Creating service run scripts..."

# Create run script for Wyoming Whisper
cat > run-whisper-uvx.sh << 'EOF'
#!/bin/bash
echo "Starting Wyoming Whisper on port 10300..."
uvx --from wyoming-faster-whisper wyoming-faster-whisper \
    --model tiny-int8 \
    --language en \
    --uri 'tcp://0.0.0.0:10300' \
    --data-dir ./whisper-data \
    --download-dir ./whisper-data
EOF

# Create run script for Wyoming Piper
cat > run-piper-uvx.sh << 'EOF'
#!/bin/bash
echo "Starting Wyoming Piper on port 10200..."

# Create wrapper script for piper using uvx
if [ ! -f "./piper-uv-wrapper.sh" ]; then
    cat > piper-uv-wrapper.sh << 'WRAPPER'
#!/bin/bash
exec uvx --from piper-tts piper "$@"
WRAPPER
    chmod +x piper-uv-wrapper.sh
fi

# Download voice if not present using uvx
if [ ! -d "./piper-data/en_US-lessac-medium" ]; then
    echo "Downloading voice model..."
    mkdir -p piper-data
    cd piper-data
    uvx --from piper-tts python -m piper.download_voices en_US-lessac-medium
    cd ..
fi

# Run Wyoming Piper using uvx wrapper
uvx --from wyoming-piper wyoming-piper \
    --piper './piper-uv-wrapper.sh' \
    --voice en_US-lessac-medium \
    --uri 'tcp://0.0.0.0:10200' \
    --data-dir ./piper-data \
    --download-dir ./piper-data
EOF

# Create run script for Wyoming OpenWakeWord
cat > run-openwakeword-uvx.sh << 'EOF'
#!/bin/bash
echo "Starting Wyoming OpenWakeWord on port 10400..."
uvx --from wyoming-openwakeword wyoming-openwakeword \
    --uri 'tcp://0.0.0.0:10400' \
    --preload-model 'ok_nabu'
EOF

chmod +x run-whisper-uvx.sh
chmod +x run-piper-uvx.sh
chmod +x run-openwakeword-uvx.sh

# Create a combined startup script
cat > start-all-services.sh << 'EOF'
#!/bin/bash

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "Installing tmux..."
    brew install tmux
fi

# Start tmux session
SESSION_NAME="agent-cli-services"

# Kill existing session if it exists
tmux kill-session -t $SESSION_NAME 2>/dev/null

# Create new session
tmux new-session -d -s $SESSION_NAME -n services

# Split window into 4 panes
tmux split-window -h -t $SESSION_NAME:services
tmux split-window -v -t $SESSION_NAME:services.0
tmux split-window -v -t $SESSION_NAME:services.1

# Run services in each pane
tmux send-keys -t $SESSION_NAME:services.0 "ollama serve" C-m
tmux send-keys -t $SESSION_NAME:services.1 "./run-whisper-uvx.sh" C-m
tmux send-keys -t $SESSION_NAME:services.2 "./run-piper-uvx.sh" C-m
tmux send-keys -t $SESSION_NAME:services.3 "./run-openwakeword-uvx.sh" C-m

# Attach to session
echo "Starting all services in tmux session '$SESSION_NAME'..."
echo "Use 'Ctrl-B d' to detach from the session"
echo "Use 'tmux attach -t $SESSION_NAME' to reattach"
tmux attach -t $SESSION_NAME
EOF

chmod +x start-all-services.sh

echo ""
echo "Setup complete! You can now run the services:"
echo ""
echo "Option 1 - Run all services at once:"
echo "  ./start-all-services.sh"
echo ""
echo "Option 2 - Run services individually:"
echo "  1. Ollama: ollama serve"
echo "  2. Whisper: ./run-whisper-uvx.sh"
echo "  3. Piper: ./run-piper-uvx.sh"
echo "  4. OpenWakeWord: ./run-openwakeword-uvx.sh"
echo ""
echo "Note: This simple setup uses uvx to run the Wyoming services directly"
echo "without needing to clone repositories or manage virtual environments."
