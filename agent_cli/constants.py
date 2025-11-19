"""Default configuration settings for the Agent CLI package."""

from __future__ import annotations

# --- Audio Configuration ---
AUDIO_FORMAT_STR = "int16"  # sounddevice/numpy format
AUDIO_FORMAT_WIDTH = 2  # 2 bytes (16-bit)
AUDIO_CHANNELS = 1
AUDIO_RATE = 16000
AUDIO_CHUNK_SIZE = 1024

# Standard Wyoming audio configuration
WYOMING_AUDIO_CONFIG = {
    "rate": AUDIO_RATE,
    "width": AUDIO_FORMAT_WIDTH,
    "channels": AUDIO_CHANNELS,
}
