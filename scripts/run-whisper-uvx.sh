#!/bin/bash
echo "Starting Wyoming Whisper on port 10300..."
uvx --from wyoming-faster-whisper wyoming-faster-whisper \
    --model tiny-int8 \
    --language en \
    --uri 'tcp://0.0.0.0:10300' \
    --data-dir ./whisper-data \
    --download-dir ./whisper-data
