#!/bin/bash
echo "🔊 Starting Wyoming Piper on port 10200..."

# Create .runtime directory and wrapper script for piper using uvx
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCRIPT_DIR/.runtime"

# Always regenerate wrapper to ensure correct Python version and output format
cat > "$SCRIPT_DIR/.runtime/piper-uv-wrapper.sh" << 'WRAPPER'
#!/bin/bash
# Run piper and capture its output
output=$(uvx --python 3.12 --from piper-tts piper "$@" 2>&1)
exit_code=$?

# Extract the filename from the output and print just the filename
# Wyoming-piper expects just the filename, not the full log message
if [[ $output =~ /tmp/[0-9]+\.wav ]]; then
    echo "$output" | grep -o '/tmp/[0-9]*\.wav' | tail -1
else
    # If we can't parse the output, print it as-is for debugging
    echo "$output" >&2
fi

exit $exit_code
WRAPPER
chmod +x "$SCRIPT_DIR/.runtime/piper-uv-wrapper.sh"

# Download voice if not present using uvx
if [ ! -d "$SCRIPT_DIR/.runtime/piper-data/en_US-lessac-medium" ]; then
    echo "⬇️ Downloading voice model..."
    mkdir -p "$SCRIPT_DIR/.runtime/piper-data"
    cd "$SCRIPT_DIR/.runtime/piper-data"
    uvx --python 3.12 --from piper-tts python -m piper.download_voices en_US-lessac-medium
    cd "$SCRIPT_DIR"
fi

# Run Wyoming Piper using uvx wrapper
uvx --python 3.12 --from wyoming-piper wyoming-piper \
    --piper "$SCRIPT_DIR/.runtime/piper-uv-wrapper.sh" \
    --voice en_US-lessac-medium \
    --uri 'tcp://0.0.0.0:10200' \
    --data-dir "$SCRIPT_DIR/.runtime/piper-data" \
    --download-dir "$SCRIPT_DIR/.runtime/piper-data" \
    --debug
