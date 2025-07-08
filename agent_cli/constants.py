"""Default configuration settings for the Agent CLI package."""

from __future__ import annotations

import pyaudio

# --- PyAudio Configuration ---
PYAUDIO_FORMAT = pyaudio.paInt16
PYAUDIO_CHANNELS = 1
PYAUDIO_RATE = 16000
PYAUDIO_CHUNK_SIZE = 1024

# Standard Wyoming audio configuration
WYOMING_AUDIO_CONFIG = {
    "rate": PYAUDIO_RATE,
    "width": 2,  # 16-bit audio
    "channels": PYAUDIO_CHANNELS,
}
