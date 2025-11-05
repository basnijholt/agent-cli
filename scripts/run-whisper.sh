#!/usr/bin/env bash
echo "🎤 Starting Wyoming Whisper on port 10300..."

# Detect if CUDA is available
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    echo "⚡ NVIDIA GPU detected, using CUDA acceleration..."
    DEVICE="cuda"
    MODEL="large-v3"
else
    echo "💻 No GPU detected or CUDA unavailable, using CPU..."
    DEVICE="cpu"
    MODEL="tiny-int8"
fi

# Create .runtime directory for whisper data
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCRIPT_DIR/.runtime"

uvx --python 3.12 \
    --from git+https://github.com/rhasspy/wyoming-faster-whisper.git@v3.0.1 \
    wyoming-faster-whisper \
    --model "$MODEL" \
    --language en \
    --device "$DEVICE" \
    --uri 'tcp://0.0.0.0:10300' \
    --data-dir "$SCRIPT_DIR/.runtime/whisper-data" \
    --download-dir "$SCRIPT_DIR/.runtime/whisper-data"
