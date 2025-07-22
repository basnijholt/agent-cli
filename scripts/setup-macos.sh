#!/bin/bash

set -e

echo "Setting up agent-cli services on macOS..."

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Homebrew is not installed. Please install Homebrew first:"
    echo "/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

# Check if Git is installed
if ! command -v git &> /dev/null; then
    echo "Installing Git..."
    brew install git
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Installing with Homebrew..."
    brew install python@3.11
fi

# Install Ollama
echo "Installing Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "Please download and install Ollama from https://ollama.com/download"
    echo "Ollama requires macOS 12 Monterey or later"
    echo "After installation, run 'ollama serve' to start the server"
    read -p "Press Enter when Ollama is installed..."
else
    echo "Ollama is already installed"
fi

# Create services directory
mkdir -p services
cd services

# Clone Wyoming services
echo "Cloning Wyoming services..."

# Wyoming Faster Whisper
if [ ! -d "wyoming-faster-whisper" ]; then
    echo "Cloning wyoming-faster-whisper..."
    git clone https://github.com/rhasspy/wyoming-faster-whisper.git
fi

# Wyoming Piper
if [ ! -d "wyoming-piper" ]; then
    echo "Cloning wyoming-piper..."
    git clone https://github.com/rhasspy/wyoming-piper.git
fi

# Wyoming OpenWakeWord
if [ ! -d "wyoming-openwakeword" ]; then
    echo "Cloning wyoming-openwakeword..."
    git clone https://github.com/rhasspy/wyoming-openwakeword.git
fi

# Setup Wyoming Faster Whisper
echo "Setting up Wyoming Faster Whisper..."
cd wyoming-faster-whisper
script/setup
cd ..

# Setup Wyoming Piper
echo "Setting up Wyoming Piper..."
cd wyoming-piper
script/setup

# Download Piper binary for macOS
echo "Downloading Piper binary..."
PIPER_VERSION="1.2.0"
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    # For Apple Silicon
    PIPER_ARCH="arm64"
elif [ "$ARCH" = "x86_64" ]; then
    # For Intel Macs
    PIPER_ARCH="amd64"
else
    echo "Unsupported architecture: $ARCH"
    exit 1
fi

# Note: Piper doesn't provide macOS binaries, we'll need to build from source
echo "Building Piper from source (this may take a while)..."
if [ ! -d "piper" ]; then
    git clone https://github.com/rhasspy/piper.git
    cd piper
    # Install build dependencies
    brew install cmake
    make
    cd ..
fi
cd ..

# Setup Wyoming OpenWakeWord
echo "Setting up Wyoming OpenWakeWord..."
cd wyoming-openwakeword
script/setup
cd ..

# Create convenience run scripts
cd ..

# Create run script for Wyoming Whisper
cat > run-whisper.sh << 'EOF'
#!/bin/bash
cd services/wyoming-faster-whisper
source .venv/bin/activate
python -m wyoming_faster_whisper \
    --model tiny-int8 \
    --language en \
    --uri 'tcp://0.0.0.0:10300' \
    --data-dir ./data \
    --download-dir ./data
EOF

# Create run script for Wyoming Piper
cat > run-piper.sh << 'EOF'
#!/bin/bash
cd services/wyoming-piper
source .venv/bin/activate

# Use the built piper binary if available
PIPER_BIN="../piper/build/piper"
if [ ! -f "$PIPER_BIN" ]; then
    echo "Piper binary not found. Please build Piper first."
    exit 1
fi

python -m wyoming_piper \
    --piper "$PIPER_BIN" \
    --voice en_US-lessac-medium \
    --uri 'tcp://0.0.0.0:10200' \
    --data-dir ./data \
    --download-dir ./data
EOF

# Create run script for Wyoming OpenWakeWord
cat > run-openwakeword.sh << 'EOF'
#!/bin/bash
cd services/wyoming-openwakeword
source .venv/bin/activate
python -m wyoming_openwakeword \
    --uri 'tcp://0.0.0.0:10400' \
    --preload-model 'ok_nabu'
EOF

chmod +x run-whisper.sh
chmod +x run-piper.sh
chmod +x run-openwakeword.sh

echo ""
echo "Setup complete! To run the services:"
echo ""
echo "1. Ollama: Run 'ollama serve' in a terminal"
echo "2. Whisper: Run './run-whisper.sh' in a terminal"
echo "3. Piper: Run './run-piper.sh' in a terminal"
echo "4. OpenWakeWord: Run './run-openwakeword.sh' in a terminal"
echo ""
echo "Note: If Piper build fails, you can use Docker instead or try building manually."
echo "The Wyoming services provide proper protocol support for agent-cli."
