#!/usr/bin/env bash

set -e

echo "🚀 Setting up agent-cli services on macOS..."

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew is not installed. Please install Homebrew first:"
    echo "/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    brew install uv
fi

# Install Ollama
echo "🧠 Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "🍺 Installing Ollama via Homebrew..."
    brew install ollama
    echo "✅ Ollama installed successfully"
else
    echo "✅ Ollama is already installed"
fi

# Check if zellij is installed
if ! command -v zellij &> /dev/null; then
    echo "📺 Installing zellij..."
    brew install zellij
fi

# Install agent-cli
echo "🤖 Installing/upgrading agent-cli..."
uv tool install --upgrade agent-cli

# Start Ollama as a background service
echo "🧠 Starting Ollama as a background service..."
brew services start ollama

# Preload default Ollama model
echo "⬇️ Preloading default Ollama model (gemma3:4b)..."
echo "⏳ This may take a few minutes depending on your internet connection..."
sleep 2  # Give Ollama service time to start
ollama pull gemma3:4b

# Install wyoming-mlx-whisper as a launchd service (Apple Silicon only)
if [ "$(uname -m)" = "arm64" ]; then
    echo "🎤 Installing wyoming-mlx-whisper as a background service..."
    echo "   This will run speech-to-text on Apple Silicon using MLX"
    curl -fsSL https://raw.githubusercontent.com/basnijholt/wyoming-mlx-whisper/main/scripts/install_service.sh | bash
    echo "✅ wyoming-mlx-whisper installed as launchd service"
else
    echo "ℹ️ Skipping wyoming-mlx-whisper service (Intel Mac - use Linux-style setup)"
fi

echo ""
echo "✅ Setup complete! You can now run the services:"
echo ""
echo "Option 1 - Run all services at once:"
echo "  ./start-all-services.sh"
echo ""
echo "Option 2 - Run services individually:"
echo "  1. Ollama: running as brew service (brew services start ollama)"
if [ "$(uname -m)" = "arm64" ]; then
    echo "  2. Whisper: running as launchd service (wyoming-mlx-whisper)"
else
    echo "  2. Whisper: ./run-whisper.sh"
fi
echo "  3. Piper: ./run-piper.sh"
echo "  4. OpenWakeWord: ./run-openwakeword.sh"
echo ""
echo "🎉 agent-cli has been installed and is ready to use!"
