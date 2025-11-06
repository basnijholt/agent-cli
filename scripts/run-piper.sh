#!/usr/bin/env bash
echo "🔊 Starting Wyoming Piper on port 10200..."

# Create .runtime directory for local assets
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCRIPT_DIR/.runtime"

# Download voice if not present using uvx
if [ ! -d "$SCRIPT_DIR/.runtime/piper-data/en_US-lessac-medium" ]; then
    echo "⬇️ Downloading voice model..."
    mkdir -p "$SCRIPT_DIR/.runtime/piper-data"
    cd "$SCRIPT_DIR/.runtime/piper-data"
    uvx --python 3.12 --from piper-tts python -m piper.download_voices en_US-lessac-medium
    cd "$SCRIPT_DIR"
fi

# Run Wyoming Piper using uvx wrapper
uvx --python 3.12 \
    --from git+https://github.com/rhasspy/wyoming-piper.git@v2.1.1 \
    wyoming-piper \
    --voice en_US-lessac-medium \
    --uri 'tcp://0.0.0.0:10200' \
    --data-dir "$SCRIPT_DIR/.runtime/piper-data" \
    --download-dir "$SCRIPT_DIR/.runtime/piper-data"
