#!/bin/bash

set -e

echo "Setting up agent-cli services on macOS..."

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

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "Installing tmux..."
    brew install tmux
fi

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
echo "  4. OpenWakeWord: ./run-openwakeword-uvx.sh (Note: may not work on macOS)"
echo ""
echo "Note: Services use uvx to run without needing virtual environments."
