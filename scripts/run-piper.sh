#!/usr/bin/env bash
echo "🔊 Starting Wyoming Piper on port 10200..."

# Create .runtime directory and wrapper script for piper using uvx
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCRIPT_DIR/.runtime"

if [ ! -f "$SCRIPT_DIR/.runtime/piper-uv-wrapper.sh" ]; then
    cat > "$SCRIPT_DIR/.runtime/piper-uv-wrapper.sh" << 'WRAPPER'
#!/usr/bin/env bash
exec uvx --from piper-tts piper "$@"
WRAPPER
    chmod +x "$SCRIPT_DIR/.runtime/piper-uv-wrapper.sh"
fi

# Download voice if not present using uvx
if [ ! -d "$SCRIPT_DIR/.runtime/piper-data/en_US-lessac-medium" ]; then
    echo "⬇️ Downloading voice model..."
    mkdir -p "$SCRIPT_DIR/.runtime/piper-data"
    cd "$SCRIPT_DIR/.runtime/piper-data"
    uvx --from piper-tts python -m piper.download_voices en_US-lessac-medium
    cd "$SCRIPT_DIR"
fi

# Run Wyoming Piper using uvx wrapper
uvx --from wyoming-piper wyoming-piper \
    --piper "$SCRIPT_DIR/.runtime/piper-uv-wrapper.sh" \
    --voice en_US-lessac-medium \
    --uri 'tcp://0.0.0.0:10200' \
    --data-dir "$SCRIPT_DIR/.runtime/piper-data" \
    --download-dir "$SCRIPT_DIR/.runtime/piper-data"
