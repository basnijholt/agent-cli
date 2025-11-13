#!/usr/bin/env bash

set -e

echo "🚀 Setting up agent-cli services on Linux..."

# Function to install uv based on the distribution
install_uv() {
    if command -v curl &> /dev/null; then
        echo "📦 Installing uv using curl..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # Add to PATH for current session
        export PATH="$HOME/.local/bin:$PATH"
    else
        echo "curl not found. Please install curl first:"
        echo "  Ubuntu/Debian: sudo apt install curl"
        echo "  Fedora/RHEL: sudo dnf install curl"
        exit 1
    fi
}

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    install_uv
fi

# Check for PortAudio (required for audio processing)
echo "🔊 Checking PortAudio..."
if ! pkg-config --exists portaudio-2.0 2>/dev/null; then
    echo "❌ ERROR: PortAudio development libraries are not installed."
    echo ""
    echo "PyAudio requires PortAudio. Install using your distribution's package manager:"
    echo ""
    echo "Ubuntu/Debian:"
    echo "  sudo apt install portaudio19-dev"
    echo ""
    echo "Fedora/RHEL/CentOS:"
    echo "  sudo dnf install portaudio-devel"
    echo ""
    echo "Arch Linux:"
    echo "  sudo pacman -S portaudio"
    echo ""
    echo "openSUSE:"
    echo "  sudo zypper install portaudio-devel"
    echo ""
    echo "After installing PortAudio, run this script again."
    exit 1
else
    echo "✅ PortAudio is already installed"
fi

# Install Ollama
echo "🧠 Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "📦 Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
    echo "✅ Ollama installed successfully"
else
    echo "✅ Ollama is already installed"
fi

# Check if zellij is available or offer alternatives
if ! command -v zellij &> /dev/null; then
    echo "📺 Zellij not found. Installing..."

    # Try different installation methods based on what's available
    if command -v cargo &> /dev/null; then
        echo "🦀 Installing zellij via cargo..."
        cargo install zellij
    elif command -v flatpak &> /dev/null; then
        echo "📦 Installing zellij via flatpak..."
        flatpak install -y flathub org.zellij_developers.zellij
    else
        echo "📥 Installing zellij binary..."
        curl -L https://github.com/zellij-org/zellij/releases/latest/download/zellij-x86_64-unknown-linux-musl.tar.gz | tar -xz -C ~/.local/bin/
        chmod +x ~/.local/bin/zellij
        export PATH="$HOME/.local/bin:$PATH"
    fi
fi

# Install agent-cli
echo "🤖 Installing/upgrading agent-cli..."
uv tool install --upgrade agent-cli

# Preload default Ollama model
echo "⬇️ Preloading default Ollama model (gemma3:4b)..."
echo "⏳ This may take a few minutes depending on your internet connection..."
# Start Ollama in background, then pull model synchronously
(ollama serve >/dev/null 2>&1 &) && sleep 2 && ollama pull gemma3:4b
# Stop the temporary ollama server
pkill -f "ollama serve" || true

echo ""
echo "✅ Setup complete! You can now run the services:"
echo ""
echo "Option 1 - Run all services at once:"
echo "  scripts/start-all-services.sh"
echo ""
echo "Option 2 - Run services individually:"
echo "  1. Ollama: ollama serve"
echo "  2. Whisper: scripts/run-whisper.sh"
echo "  3. Piper: scripts/run-piper.sh"
echo "  4. OpenWakeWord: scripts/run-openwakeword.sh"
echo ""
echo "📝 Note: Services use uvx to run without needing virtual environments."
echo "For GPU acceleration, make sure NVIDIA drivers and CUDA are installed."
echo "🎉 agent-cli has been installed and is ready to use!"
