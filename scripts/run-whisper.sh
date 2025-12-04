#!/usr/bin/env bash
echo "🎤 Starting Wyoming Whisper on port 10300..."

# Create .runtime directory for whisper data
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCRIPT_DIR/.runtime"

# Detect platform
OS="$(uname -s)"

if [ "$OS" = "Darwin" ]; then
    # macOS: Use MLX-based Whisper for Apple Silicon optimization
    echo "🍎 macOS detected, using MLX Whisper for Apple Silicon"

    DEFAULT_MODEL="mlx-community/whisper-large-v3-turbo"
    MODEL="${WHISPER_MODEL:-$DEFAULT_MODEL}"
    echo "📦 Using model: $MODEL"

    uvx --python 3.12 \
        --from git+https://github.com/vincent861223/wyoming-mlx-whisper.git \
        wyoming-mlx-whisper \
        --model "$MODEL" \
        --uri 'tcp://0.0.0.0:10300'
else
    # Linux: Use faster-whisper with CUDA/CPU detection
    if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
        echo "⚡ NVIDIA GPU detected"
        DETECTED_DEVICE="cuda"
    else
        echo "💻 No GPU detected or CUDA unavailable"
        DETECTED_DEVICE="cpu"
    fi

    # Allow device override via environment variable
    DEVICE="${WHISPER_DEVICE:-$DETECTED_DEVICE}"

    # Set default model based on final device choice
    if [ "$DEVICE" = "cuda" ]; then
        DEFAULT_MODEL="large-v3"
    else
        DEFAULT_MODEL="tiny"
    fi

    # Allow model override via environment variable
    MODEL="${WHISPER_MODEL:-$DEFAULT_MODEL}"
    echo "📦 Using model: $MODEL on device: $DEVICE"

    uvx --python 3.12 \
        --from git+https://github.com/rhasspy/wyoming-faster-whisper.git@v3.0.1 \
        wyoming-faster-whisper \
        --model "$MODEL" \
        --language en \
        --device "$DEVICE" \
        --uri 'tcp://0.0.0.0:10300' \
        --data-dir "$SCRIPT_DIR/.runtime/whisper-data" \
        --download-dir "$SCRIPT_DIR/.runtime/whisper-data"
fi
