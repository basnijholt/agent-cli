"""Default configuration settings for the Agent CLI package."""

from __future__ import annotations

import os

import pyaudio

# --- ASR (Wyoming) Configuration ---
ASR_SERVER_IP = os.getenv("ASR_SERVER_IP", "localhost")
ASR_SERVER_PORT = 10300

# --- TTS (Wyoming Piper) Configuration ---
TTS_SERVER_IP = os.getenv("TTS_SERVER_IP", "localhost")
TTS_SERVER_PORT = 10200

# --- Wake Word (Wyoming) Configuration ---
WAKE_WORD_SERVER_IP = os.getenv("WAKE_WORD_SERVER_IP", "localhost")
WAKE_WORD_SERVER_PORT = 10400

# --- Ollama LLM Configuration ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = "devstral:24b"

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
