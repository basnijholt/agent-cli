#!/bin/bash
echo "Starting Wyoming Piper on port 10200..."

# Create wrapper script for piper using uvx
if [ ! -f "./piper-uv-wrapper.sh" ]; then
    cat > piper-uv-wrapper.sh << 'WRAPPER'
#!/bin/bash
exec uvx --from piper-tts piper "$@"
WRAPPER
    chmod +x piper-uv-wrapper.sh
fi

# Download voice if not present using uvx
if [ ! -d "./piper-data/en_US-lessac-medium" ]; then
    echo "Downloading voice model..."
    mkdir -p piper-data
    cd piper-data
    uvx --from piper-tts python -m piper.download_voices en_US-lessac-medium
    cd ..
fi

# Run Wyoming Piper using uvx wrapper
uvx --from wyoming-piper wyoming-piper \
    --piper './piper-uv-wrapper.sh' \
    --voice en_US-lessac-medium \
    --uri 'tcp://0.0.0.0:10200' \
    --data-dir ./piper-data \
    --download-dir ./piper-data
