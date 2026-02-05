#!/usr/bin/env bash
echo "👂 Starting Wyoming OpenWakeWord on port 10400..."

# Use the LiteRT fork because upstream depends on tflite-runtime-nightly
# which lacks Python 3.12+ wheels. This fork uses ai-edge-litert instead.
# See: https://github.com/rhasspy/wyoming-openwakeword/pull/43

uvx --python 3.12 --from git+https://github.com/basnijholt/wyoming-openwakeword.git@litert \
    wyoming-openwakeword \
    --uri 'tcp://0.0.0.0:10400' \
    --preload-model 'ok_nabu'
