#!/bin/bash

set -e

echo "🚀 Setting up agent-cli services on macOS..."

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Homebrew is not installed. Please install Homebrew first:"
    echo "/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    brew install uv
fi

# Check for PortAudio (required for audio processing)
echo "🔊 Checking PortAudio..."
if ! pkg-config --exists portaudio-2.0 2>/dev/null; then
    echo "Installing PortAudio..."
    brew install portaudio
else
    echo "PortAudio is already installed"
fi

# Install Ollama
echo "🧠 Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "Installing Ollama via Homebrew..."
    brew install ollama
    echo "Ollama installed successfully"
else
    echo "Ollama is already installed"
fi

# Check if zellij is installed
if ! command -v zellij &> /dev/null; then
    echo "📺 Installing zellij..."
    brew install zellij
fi

# Install agent-cli
echo "🤖 Installing/upgrading agent-cli..."
uv tool install --upgrade agent-cli

# Preload default Ollama model
echo "⬇️ Preloading default Ollama model (qwen3:4b)..."
echo "This may take a few minutes depending on your internet connection..."
# Start Ollama in background, then pull model
(ollama serve >/dev/null 2>&1 &) && sleep 2 && ollama pull qwen3:4b &
OLLAMA_PID=$!

echo ""
echo "✅ Setup complete! You can now run the services:"
echo "Note: Ollama model download is running in background (PID: $OLLAMA_PID)"
echo ""
echo "Option 1 - Run all services at once:"
echo "  ./start-all-services.sh"
echo ""
echo "Option 2 - Run services individually:"
echo "  1. Ollama: ollama serve"
echo "  2. Whisper: ./run-whisper.sh"
echo "  3. Piper: ./run-piper.sh"
echo "  4. OpenWakeWord: ./run-openwakeword.sh"
echo ""
echo "Note: Services use uvx to run without needing virtual environments."
echo "agent-cli has been installed and is ready to use!"
