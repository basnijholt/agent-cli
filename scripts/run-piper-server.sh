#!/bin/bash
echo "🔊 Starting Piper HTTP server on port 10200..."

# Create .runtime directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCRIPT_DIR/.runtime"

# Download voice if not present using uvx
if [ ! -d "$SCRIPT_DIR/.runtime/piper-data/en_US-lessac-medium" ]; then
    echo "⬇️ Downloading voice model..."
    mkdir -p "$SCRIPT_DIR/.runtime/piper-data"
    cd "$SCRIPT_DIR/.runtime/piper-data"
    uvx --from piper-tts python -m piper.download_voices en_US-lessac-medium
    cd "$SCRIPT_DIR"
fi

# Run Piper HTTP server using uvx with Flask dependency
uvx --with flask --from piper-tts python -m piper.http_server -m $SCRIPT_DIR/.runtime/piper-data/en_US-lessac-medium --port 10200
