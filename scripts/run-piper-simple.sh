#!/bin/bash
echo "🔊 Starting Wyoming Piper on port 10200 (Simple Mode)..."

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$SCRIPT_DIR/.runtime"
PIPER_DATA_DIR="$RUNTIME_DIR/piper-data"
VOICE_MODEL="en_US-lessac-medium"

mkdir -p "$RUNTIME_DIR" "$PIPER_DATA_DIR"

# Create a Python virtual environment using system python
if [ ! -d "$RUNTIME_DIR/piper-env" ]; then
    echo "🐍 Creating Python virtual environment..."
    # Try to use Python 3.11 or 3.12 if available, fallback to 3.10
    if command -v python3.11 &> /dev/null; then
        python3.11 -m venv "$RUNTIME_DIR/piper-env"
    elif command -v python3.12 &> /dev/null; then
        python3.12 -m venv "$RUNTIME_DIR/piper-env"
    elif command -v python3.10 &> /dev/null; then
        python3.10 -m venv "$RUNTIME_DIR/piper-env"
    else
        echo "⚠️ Using system Python (may have compatibility issues)"
        python3 -m venv "$RUNTIME_DIR/piper-env"
    fi
fi

# Activate the virtual environment
source "$RUNTIME_DIR/piper-env/bin/activate"

# Install packages using pip in the virtual environment
echo "📦 Installing piper-tts and wyoming-piper..."
pip install --upgrade pip
pip install piper-tts wyoming-piper requests

# Download voice model if not present
if [ ! -d "$PIPER_DATA_DIR/$VOICE_MODEL" ]; then
    echo "⬇️ Downloading voice model $VOICE_MODEL..."
    mkdir -p "$PIPER_DATA_DIR/$VOICE_MODEL"

    cd "$PIPER_DATA_DIR"
    python -c "
import requests
import os
from pathlib import Path

model_url = 'https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx'
config_url = 'https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json'

model_dir = Path('$VOICE_MODEL')
model_dir.mkdir(exist_ok=True)

print('Downloading model file...')
try:
    r = requests.get(model_url, timeout=120)
    r.raise_for_status()
    with open(model_dir / 'en_US-lessac-medium.onnx', 'wb') as f:
        f.write(r.content)
    print('✅ Model file downloaded')
except Exception as e:
    print(f'❌ Failed to download model file: {e}')
    raise

print('Downloading config file...')
try:
    r = requests.get(config_url, timeout=120)
    r.raise_for_status()
    with open(model_dir / 'en_US-lessac-medium.onnx.json', 'wb') as f:
        f.write(r.content)
    print('✅ Config file downloaded')
except Exception as e:
    print(f'❌ Failed to download config file: {e}')
    raise

print('✅ Voice model downloaded successfully')
"
    cd "$SCRIPT_DIR"
else
    echo "✅ Voice model already exists"
fi

# Start Wyoming Piper
echo "🚀 Starting Wyoming Piper server..."
"$RUNTIME_DIR/piper-env/bin/python" -m wyoming_piper \
    --piper "$RUNTIME_DIR/piper-env/bin/piper" \
    --voice "$VOICE_MODEL" \
    --uri 'tcp://0.0.0.0:10200' \
    --data-dir "$PIPER_DATA_DIR" \
    --download-dir "$PIPER_DATA_DIR"
