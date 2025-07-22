#!/bin/bash
echo "Starting Wyoming OpenWakeWord on port 10400..."

# Check if we're on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Note: OpenWakeWord on macOS requires LiteRT support."
    echo "This is available in the PR: https://github.com/rhasspy/wyoming-openwakeword/pull/XXX"
    echo "Until merged, please use the forked version with:"
    echo "  uvx --from git+https://github.com/YOUR-USERNAME/wyoming-openwakeword.git@litert-support wyoming-openwakeword"
    echo ""
fi

uvx --from wyoming-openwakeword --prerelease=allow wyoming-openwakeword \
    --uri 'tcp://0.0.0.0:10400' \
    --preload-model 'ok_nabu'
