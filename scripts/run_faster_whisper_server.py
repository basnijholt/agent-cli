#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "typer>=0.12",
#   "fastapi>=0.115",
#   "uvicorn>=0.30",
#   "python-multipart>=0.0.9",
#   "faster-whisper>=1.1.1",
# ]
# ///

"""Minimal FastAPI server exposing faster-whisper transcription.

Run directly with uv:

  ./scripts/run_faster_whisper_server.py --model large-v3 --host 0.0.0.0 --port 8811

Then point agent-cli at it, e.g.:

  agent-cli transcribe --asr-openai-base-url http://localhost:8811/v1 --asr-openai-model large-v3

Note: agent-cli requires a `--asr-openai-model` value in the request, but this server ignores it and always uses the model you start it with (`--model`).
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel

# Defaults configurable via environment if desired.
DEFAULT_MODEL = "large-v3"
DEFAULT_HOST = "0.0.0.0"  # noqa: S104
DEFAULT_PORT = 8811
DEFAULT_DEVICE = "auto"
DEFAULT_COMPUTE_TYPE = "default"
DEFAULT_LOG_LEVEL = "info"


class ModelHolder:
    """Thread-safe lazy model loader so we only download/init once."""

    def __init__(self, model_id: str, device: str, compute_type: str) -> None:
        """Store model configuration."""
        self.model_id = model_id
        self.device = device
        self.compute_type = compute_type
        self._model: WhisperModel | None = None
        self._lock = threading.Lock()

    def get(self) -> WhisperModel:
        """Load or return the cached WhisperModel instance."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = WhisperModel(
                        self.model_id,
                        device=self.device,
                        compute_type=self.compute_type,
                    )
        return self._model


def build_api(holder: ModelHolder) -> FastAPI:
    """Create the FastAPI app wired to the provided model holder."""
    api = FastAPI(title="faster-whisper-api")

    @api.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "model": holder.model_id,
            "device": holder.device,
            "compute_type": holder.compute_type,
        }

    @api.post("/v1/audio/transcriptions")
    async def transcribe(
        file: Annotated[UploadFile, File(..., description="Audio file (wav, mp3, m4a, etc.)")],
        language: str | None = None,
    ) -> dict[str, str]:
        audiobytes = await file.read()
        if not audiobytes:
            return JSONResponse({"error": "empty file"}, status_code=400)

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=Path(file.filename or "audio").suffix,
        ) as tmp:
            tmp.write(audiobytes)
            tmp_path = tmp.name

        try:
            model = holder.get()
            segments, info = model.transcribe(tmp_path, language=language)
            text = " ".join(seg.text.strip() for seg in segments)
            return {
                "object": "transcription",
                "model": holder.model_id,
                "language": language or info.language,
                "text": text,
            }
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return api


def main(
    model: str = typer.Option(DEFAULT_MODEL, help="faster-whisper model id"),
    host: str = typer.Option(DEFAULT_HOST, show_default=True),
    port: int = typer.Option(DEFAULT_PORT, show_default=True),
    device: str = typer.Option(DEFAULT_DEVICE, help="cpu, cuda, or auto"),
    compute_type: str = typer.Option(
        DEFAULT_COMPUTE_TYPE,
        help="faster-whisper compute_type (e.g., int8, int8_float16, float16, float32, default)",
    ),
    log_level: str = typer.Option(DEFAULT_LOG_LEVEL, help="uvicorn log level"),
) -> None:
    """Start the server with the given runtime options."""
    holder = ModelHolder(model_id=model, device=device, compute_type=compute_type)
    api = build_api(holder)
    uvicorn.run(api, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    typer.run(main)
