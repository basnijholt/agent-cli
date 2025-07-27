#!/usr/bin/env bash
echo "👂 Starting Wyoming OpenWakeWord on port 10400..."

# Use the LiteRT fork until the PR is merged
# PR: https://github.com/rhasspy/wyoming-openwakeword/pull/XXX
# This version works on macOS and other platforms without tflite-runtime

uvx --python 3.12 --from git+https://github.com/basnijholt/wyoming-openwakeword.git@litert \
    wyoming-openwakeword \
    --uri 'tcp://0.0.0.0:10400' \
    --preload-model 'ok_nabu'
