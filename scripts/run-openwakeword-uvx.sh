#!/bin/bash
echo "Starting Wyoming OpenWakeWord on port 10400..."
uvx --from wyoming-openwakeword wyoming-openwakeword \
    --uri 'tcp://0.0.0.0:10400' \
    --preload-model 'ok_nabu'
