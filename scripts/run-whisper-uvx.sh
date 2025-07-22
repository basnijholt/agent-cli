#!/bin/bash
echo "Starting Wyoming Whisper on port 10300..."

# Detect if CUDA is available
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    echo "NVIDIA GPU detected, using CUDA acceleration..."
    DEVICE="cuda"
    MODEL="large-v3"
else
    echo "No GPU detected or CUDA unavailable, using CPU..."
    DEVICE="cpu"
    MODEL="tiny-int8"
fi

uvx --from wyoming-faster-whisper wyoming-faster-whisper \
    --model "$MODEL" \
    --language en \
    --device "$DEVICE" \
    --uri 'tcp://0.0.0.0:10300' \
    --data-dir ./whisper-data \
    --download-dir ./whisper-data
