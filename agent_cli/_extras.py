"""Extras metadata for optional dependencies.

Auto-generated from pyproject.toml. DO NOT EDIT MANUALLY.

Regenerate with: python scripts/sync_extras.py
"""

from __future__ import annotations

# Extra name -> (description, list of import names to check)
# Import names use Python module notation (e.g., "google.genai" not "google-genai")
EXTRAS: dict[str, tuple[str, list[str]]] = {
    "audio": ("Audio recording/playback", ["sounddevice"]),
    "gemini": ("Google Gemini provider", ["google.genai"]),
    "llm": ("LLM framework (pydantic-ai)", ["pydantic_ai"]),
    "memory": ("Long-term memory proxy", ["chromadb", "yaml"]),
    "openai": ("OpenAI API provider", ["openai"]),
    "rag": ("RAG proxy (ChromaDB, embeddings)", ["chromadb"]),
    "server": ("FastAPI server components", ["fastapi"]),
    "speed": ("Audio speed adjustment (audiostretchy)", ["audiostretchy"]),
    "tts": ("Local Piper TTS", ["piper"]),
    "tts-kokoro": ("Kokoro neural TTS", ["kokoro"]),
    "vad": ("Voice Activity Detection (silero-vad)", ["silero_vad"]),
    "whisper": ("Local Whisper ASR (faster-whisper)", ["faster_whisper"]),
    "whisper-mlx": ("MLX Whisper for Apple Silicon", ["mlx_whisper"]),
    "wyoming": ("Wyoming protocol support", ["wyoming"]),
}
