#!/bin/bash

set -e

echo "Setting up agent-cli services on Linux..."

# Function to install uv based on the distribution
install_uv() {
    if command -v curl &> /dev/null; then
        echo "Installing uv using curl..."
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
    echo "Installing uv..."
    install_uv
fi

# Install Ollama
echo "Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
    echo "Ollama installed successfully"
else
    echo "Ollama is already installed"
fi

# Check if zellij is available or offer alternatives
if ! command -v zellij &> /dev/null; then
    echo "Zellij not found. Installing..."

    # Try different installation methods based on what's available
    if command -v cargo &> /dev/null; then
        echo "Installing zellij via cargo..."
        cargo install zellij
    elif command -v flatpak &> /dev/null; then
        echo "Installing zellij via flatpak..."
        flatpak install -y flathub org.zellij_developers.zellij
    else
        echo "Installing zellij binary..."
        curl -L https://github.com/zellij-org/zellij/releases/latest/download/zellij-x86_64-unknown-linux-musl.tar.gz | tar -xz -C ~/.local/bin/
        chmod +x ~/.local/bin/zellij
        export PATH="$HOME/.local/bin:$PATH"
    fi
fi

# Install agent-cli
echo "Installing/upgrading agent-cli..."
uv tool install --upgrade agent-cli

echo ""
echo "Setup complete! You can now run the services:"
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
echo "Note: Services use uvx to run without needing virtual environments."
echo "For GPU acceleration, make sure NVIDIA drivers and CUDA are installed."
echo "agent-cli has been installed and is ready to use!"
