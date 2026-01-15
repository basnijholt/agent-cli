"""FastAPI web service for Agent CLI transcription.

This module re-exports from agent_cli.server.proxy.api for backwards compatibility.
"""

from agent_cli.server.proxy.api import (
    HealthResponse,
    TranscriptionRequest,
    TranscriptionResponse,
    app,
    health_check,
    transcribe_audio,
)

__all__ = [
    "HealthResponse",
    "TranscriptionRequest",
    "TranscriptionResponse",
    "app",
    "health_check",
    "transcribe_audio",
]
