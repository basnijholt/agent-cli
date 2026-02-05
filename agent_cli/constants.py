"""Default configuration settings for the Agent CLI package."""

from __future__ import annotations

# --- Audio Configuration ---
AUDIO_FORMAT_STR = "int16"  # sounddevice/numpy format
AUDIO_FORMAT_WIDTH = 2  # 2 bytes (16-bit)
AUDIO_CHANNELS = 1
AUDIO_RATE = 16000
AUDIO_CHUNK_SIZE = 1024
WAV_HEADER_SIZE = 44  # Standard WAV header size in bytes

# --- TTS Configuration ---
PIPER_DEFAULT_SAMPLE_RATE = 22050  # Piper TTS default sample rate
KOKORO_DEFAULT_SAMPLE_RATE = 24000  # Kokoro TTS default sample rate

# Standard Wyoming audio configuration
WYOMING_AUDIO_CONFIG = {
    "rate": AUDIO_RATE,
    "width": AUDIO_FORMAT_WIDTH,
    "channels": AUDIO_CHANNELS,
}

# --- HTTP Defaults ---
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
