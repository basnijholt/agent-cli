#!/bin/bash
echo "🎤 Starting whisper.cpp server on port 10500..."

# Detect Apple Silicon for Metal acceleration
if [[ $(uname -m) == "arm64" ]]; then
    echo "⚡ Apple Silicon detected, using Metal acceleration..."
    EXTRA_ARGS=""
else
    echo "💻 Running on Intel Mac, using CPU..."
    EXTRA_ARGS=""
fi

# Create .runtime directory for whisper data
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCRIPT_DIR/.runtime/whisper-models"

# Model selection - use base.en for good balance of speed and accuracy
# Available models: tiny.en, tiny, base.en, base, small.en, small, medium.en, medium, large-v1, large-v2, large-v3
MODEL_NAME="${WHISPER_MODEL:-base.en}"
MODEL_FILE="$SCRIPT_DIR/.runtime/whisper-models/ggml-$MODEL_NAME.bin"

# Download model if not present
if [ ! -f "$MODEL_FILE" ]; then
    echo "⬇️ Downloading whisper model: $MODEL_NAME..."
    echo "⏳ This may take a few minutes depending on your internet connection..."
    curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$MODEL_NAME.bin" \
         -o "$MODEL_FILE" \
         --progress-bar
    echo "✅ Model downloaded successfully"
fi

# Run whisper.cpp server
# --host 0.0.0.0 allows connections from any interface
# --port 10500 matches the Wyoming Whisper port for compatibility
# --convert enables audio format conversion
# --model specifies the model file
# --threads uses half the available cores for good performance
THREADS=$(($(sysctl -n hw.ncpu) / 2))

whisper-server \
    --host 0.0.0.0 \
    --port 10500 \
    --convert \
    --model "$MODEL_FILE" \
    --threads $THREADS \
    $EXTRA_ARGS