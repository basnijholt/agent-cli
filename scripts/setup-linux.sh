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
# We use pkg-config if available, otherwise fallback to checking common library paths or ldconfig
PORTAUDIO_FOUND=false
if command -v pkg-config &> /dev/null; then
    if pkg-config --exists portaudio-2.0; then
        PORTAUDIO_FOUND=true
    fi
elif /sbin/ldconfig -p 2>/dev/null | grep -q libportaudio; then
    PORTAUDIO_FOUND=true
elif [ -f /usr/include/portaudio.h ] || [ -f /usr/local/include/portaudio.h ]; then
    PORTAUDIO_FOUND=true
fi

if [ "$PORTAUDIO_FOUND" = false ]; then
    echo "❌ ERROR: PortAudio development libraries are not detected."
    echo ""
    echo "agent-cli requires PortAudio for audio recording and playback."
    echo "Please install it using your distribution's package manager:"
    echo ""
    echo "  Ubuntu/Debian:      sudo apt install portaudio19-dev python3-dev build-essential"
    echo "  Fedora/RHEL:        sudo dnf install portaudio-devel python3-devel @development-tools"
    echo "  Arch Linux:         sudo pacman -S portaudio base-devel"
    echo "  openSUSE:           sudo zypper install portaudio-devel python3-devel"
    echo "  Alpine:             sudo apk add portaudio-dev python3-dev build-base"
    echo ""
    echo "After installing PortAudio, please run this script again."
    exit 1
else
    echo "✅ PortAudio is installed"
fi

# Check for FFmpeg
echo "🎥 Checking FFmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ ERROR: FFmpeg is not installed."
    echo ""
    echo "agent-cli requires FFmpeg for audio format conversion."
    echo "Please install it using your distribution's package manager:"
    echo ""
    echo "  Ubuntu/Debian:      sudo apt install ffmpeg"
    echo "  Fedora/RHEL:        sudo dnf install ffmpeg"
    echo "  Arch Linux:         sudo pacman -S ffmpeg"
    echo "  openSUSE:           sudo zypper install ffmpeg"
    echo "  Alpine:             sudo apk add ffmpeg"
    echo ""
    echo "After installing FFmpeg, please run this script again."
    exit 1
else
    echo "✅ FFmpeg is installed"
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
