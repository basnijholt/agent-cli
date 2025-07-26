#!/bin/bash

set -e

echo "🚀 Setting up agent-cli services on macOS..."

# Check if running on Apple Silicon
IS_APPLE_SILICON=false
if [[ $(uname -s) == "Darwin" && $(uname -m) == "arm64" ]]; then
    IS_APPLE_SILICON=true
fi

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

# Check for PortAudio (required for audio processing)
echo "🔊 Checking PortAudio..."
if ! pkg-config --exists portaudio-2.0 2>/dev/null; then
    echo "📦 Installing PortAudio..."
    brew install portaudio
else
    echo "✅ PortAudio is already installed"
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

# Check if whisper-server is installed
if [["$IS_APPLE_SILICON" == "true"]]; then
    if ! command -v whisper-server &> /dev/null; then
        echo "🤫 Installing whisper-cpp..."
        brew install whisper-cpp
    fi
fi

# Install agent-cli
echo "🤖 Installing/upgrading agent-cli..."
uv tool install --upgrade agent-cli

# Create optimized config for Apple Silicon
if [[ "$IS_APPLE_SILICON" == "true" ]]; then
    echo "⚙️ Creating optimized agent-cli config for Apple Silicon..."

    # Check if config already exists
    if [[ -f "agent-cli-config.toml" ]]; then
        echo "📝 Backing up existing agent-cli-config.toml to agent-cli-config.toml.backup"
        cp agent-cli-config.toml agent-cli-config.toml.backup
    fi

    # Copy example and modify for Apple Silicon
    if [[ -f "example.agent-cli-config.toml" ]]; then
        cp example.agent-cli-config.toml agent-cli-config.toml

        # Replace asr-provider = "local" with asr-provider = "whispercpp"
        if command -v sed &> /dev/null; then
            sed -i '' 's/asr-provider = "local"/asr-provider = "whispercpp"/' agent-cli-config.toml
            echo "✅ Created agent-cli-config.toml with whispercpp ASR provider"
        else
            echo "⚠️ sed not found. Please manually change asr-provider to 'whispercpp' in agent-cli-config.toml"
        fi
    else
        echo "⚠️ example.agent-cli-config.toml not found. Skipping config creation."
    fi
else
    echo "💻 Intel Mac detected - using default configuration"
    if [[ -f "example.agent-cli-config.toml" && ! -f "agent-cli-config.toml" ]]; then
        cp example.agent-cli-config.toml agent-cli-config.toml
        echo "✅ Created agent-cli-config.toml from example"
    fi
fi

# Preload default Ollama model
echo "⬇️ Preloading default Ollama model (qwen3:4b)..."
echo "⏳ This may take a few minutes depending on your internet connection..."
# Start Ollama in background, then pull model synchronously
(ollama serve >/dev/null 2>&1 &) && sleep 2 && ollama pull qwen3:4b
# Stop the temporary ollama server
pkill -f "ollama serve" || true

echo ""
echo "✅ Setup complete! You can now run the services:"
echo ""
echo "Option 1 - Run all services at once:"
echo "  ./start-all-services.sh"
echo ""
echo "Option 2 - Run services individually:"
echo "  1. Ollama: ollama serve"
if [[ "$IS_APPLE_SILICON" == "true" ]]; then
    echo "  2. Whisper.cpp: ./run-whispercpp.sh"
else
    echo "  2. Whisper: ./run-whisper.sh"
fi
echo "  3. Piper: ./run-piper.sh"
echo "  4. OpenWakeWord: ./run-openwakeword.sh"
echo ""
echo "🎉 agent-cli has been installed and is ready to use!"
