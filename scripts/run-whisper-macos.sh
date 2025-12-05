#!/usr/bin/env bash
# macOS: MLX-based Whisper for Apple Silicon
echo "🎤 Starting Wyoming MLX Whisper on port 10300..."
echo "🍎 Using MLX for Apple Silicon optimization"

DEFAULT_MODEL="mlx-community/whisper-large-v3-turbo"
MODEL="${WHISPER_MODEL:-$DEFAULT_MODEL}"
echo "📦 Using model: $MODEL"

uvx --python 3.12 \
    --from git+https://github.com/vincent861223/wyoming-mlx-whisper.git \
    wyoming-whisper-mlx-whisper \
    --model "$MODEL" \
    --uri 'tcp://0.0.0.0:10300'
