#!/usr/bin/env bash
# Wrapper that calls the platform-specific whisper script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$(uname -s)" = "Darwin" ]; then
    exec "$SCRIPT_DIR/run-whisper-macos.sh"
else
    exec "$SCRIPT_DIR/run-whisper-linux.sh"
fi
