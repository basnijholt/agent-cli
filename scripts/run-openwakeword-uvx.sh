#!/bin/bash
echo "Starting Wyoming OpenWakeWord on port 10400..."

# Note: The official package requires tflite-runtime which is not available on macOS
# A PR is pending to switch to LiteRT: https://github.com/rhasspy/wyoming-openwakeword/pull/XXX
# Until merged, this will only work on Linux

uvx --from wyoming-openwakeword --prerelease=allow wyoming-openwakeword \
    --uri 'tcp://0.0.0.0:10400' \
    --preload-model 'ok_nabu'
