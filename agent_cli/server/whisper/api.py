"""FastAPI application for Whisper ASR server with OpenAI-compatible API."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import time
import wave
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from agent_cli import constants
from agent_cli.server.common import log_requests_middleware
from agent_cli.server.whisper import metrics

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from agent_cli.server.whisper.model_registry import WhisperModelRegistry

logger = logging.getLogger(__name__)

# Global registry - will be set by create_app()
_registry: WhisperModelRegistry | None = None
_wyoming_task: asyncio.Task[None] | None = None


def _format_timestamp(seconds: float, *, always_include_hours: bool = False) -> str:
    """Format seconds as HH:MM:SS,mmm for SRT format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)

    if always_include_hours or hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    return f"{minutes:02d}:{secs:02d},{millis:03d}"


def _format_vtt_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm for VTT format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


# --- Pydantic Models ---


class TranscriptionResponse(BaseModel):
    """OpenAI-compatible transcription response."""

    text: str


class VerboseTranscriptionResponse(BaseModel):
    """OpenAI-compatible verbose transcription response."""

    task: str
    language: str
    duration: float
    text: str
    segments: list[dict[str, Any]]


class ModelStatusResponse(BaseModel):
    """Status of a single model."""

    name: str
    loaded: bool
    device: str | None
    ttl_seconds: int
    ttl_remaining: float | None
    total_requests: int
    active_requests: int


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    models: list[ModelStatusResponse]


class UnloadResponse(BaseModel):
    """Response from model unload request."""

    status: str
    model: str
    was_loaded: bool


# --- App Factory ---


def create_app(  # noqa: C901, PLR0915
    registry: WhisperModelRegistry,
    *,
    enable_metrics: bool = True,
    enable_wyoming: bool = True,
    wyoming_uri: str = "tcp://0.0.0.0:3001",
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        registry: The model registry to use.
        enable_metrics: Whether to enable Prometheus metrics.
        enable_wyoming: Whether to start Wyoming server.
        wyoming_uri: URI for Wyoming server.

    Returns:
        Configured FastAPI application.

    """
    global _registry

    _registry = registry

    if enable_metrics:
        metrics.init_metrics()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Manage application lifecycle."""
        global _wyoming_task

        # Start the registry
        await registry.start()

        # Start Wyoming server if enabled
        if enable_wyoming:
            try:
                from agent_cli.server.whisper.wyoming_handler import (  # noqa: PLC0415
                    start_wyoming_server,
                )

                _wyoming_task = asyncio.create_task(
                    start_wyoming_server(registry, wyoming_uri),
                )
                logger.info("Started Wyoming server at %s", wyoming_uri)
            except ImportError:
                logger.warning("Wyoming not available, skipping Wyoming server")
            except Exception:
                logger.exception("Failed to start Wyoming server")

        yield

        # Stop Wyoming server
        if _wyoming_task is not None:
            _wyoming_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await _wyoming_task

        # Stop the registry
        await registry.stop()

    app = FastAPI(
        title="Whisper ASR Server",
        description="OpenAI-compatible Whisper ASR server with TTL-based model unloading",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add request logging middleware
    @app.middleware("http")
    async def log_requests(request: Any, call_next: Any) -> Any:
        """Log basic request information."""
        return await log_requests_middleware(request, call_next)

    # Add Prometheus metrics endpoint if enabled
    if enable_metrics and metrics.HAS_PROMETHEUS:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest  # noqa: PLC0415
        from starlette.responses import Response  # noqa: PLC0415

        @app.get("/metrics")
        async def prometheus_metrics() -> Response:
            """Prometheus metrics endpoint."""
            # Update model status metrics
            for status in registry.list_status():
                metrics.update_model_status(
                    status.name,
                    loaded=status.loaded,
                    ttl_remaining=status.ttl_remaining,
                    active_requests=status.active_requests,
                )
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # --- Health & Status Endpoints ---

    @app.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Health check endpoint."""
        return HealthResponse(
            status="healthy",
            models=[
                ModelStatusResponse(
                    name=s.name,
                    loaded=s.loaded,
                    device=s.device,
                    ttl_seconds=s.ttl_seconds,
                    ttl_remaining=s.ttl_remaining,
                    total_requests=s.total_requests,
                    active_requests=s.active_requests,
                )
                for s in registry.list_status()
            ],
        )

    @app.post("/v1/model/unload", response_model=UnloadResponse)
    async def unload_model(
        model: Annotated[str | None, Query(description="Model to unload")] = None,
    ) -> UnloadResponse:
        """Manually unload a model from memory."""
        try:
            manager = registry.get_manager(model)
            was_loaded = await manager.unload()
            return UnloadResponse(
                status="success",
                model=manager.config.model_name,
                was_loaded=was_loaded,
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    # --- OpenAI-Compatible Transcription Endpoints ---

    @app.post("/v1/audio/transcriptions", response_model=None)
    async def transcribe_audio(
        file: Annotated[UploadFile, File(description="Audio file to transcribe")],
        model: Annotated[str, Form(description="Model to use")] = "whisper-1",
        language: Annotated[str | None, Form(description="Language code")] = None,
        prompt: Annotated[str | None, Form(description="Initial prompt")] = None,
        response_format: Annotated[
            Literal["json", "text", "srt", "verbose_json", "vtt"],
            Form(description="Response format"),
        ] = "json",
        temperature: Annotated[float, Form(description="Sampling temperature")] = 0.0,
    ) -> TranscriptionResponse | VerboseTranscriptionResponse | PlainTextResponse:
        """OpenAI-compatible audio transcription endpoint."""
        return await _do_transcription(
            file=file,
            model=model,
            language=language,
            prompt=prompt,
            response_format=response_format,
            temperature=temperature,
            task="transcribe",
        )

    @app.post("/v1/audio/translations", response_model=None)
    async def translate_audio(
        file: Annotated[UploadFile, File(description="Audio file to translate")],
        model: Annotated[str, Form(description="Model to use")] = "whisper-1",
        prompt: Annotated[str | None, Form(description="Initial prompt")] = None,
        response_format: Annotated[
            Literal["json", "text", "srt", "verbose_json", "vtt"],
            Form(description="Response format"),
        ] = "json",
        temperature: Annotated[float, Form(description="Sampling temperature")] = 0.0,
    ) -> TranscriptionResponse | VerboseTranscriptionResponse | PlainTextResponse:
        """OpenAI-compatible audio translation endpoint (always to English)."""
        return await _do_transcription(
            file=file,
            model=model,
            language=None,  # Translation always outputs English
            prompt=prompt,
            response_format=response_format,
            temperature=temperature,
            task="translate",
        )

    async def _do_transcription(
        *,
        file: UploadFile,
        model: str,
        language: str | None,
        prompt: str | None,
        response_format: str,
        temperature: float,
        task: str,
    ) -> TranscriptionResponse | VerboseTranscriptionResponse | PlainTextResponse:
        """Perform transcription with the specified parameters."""
        # Resolve model name - "whisper-1" is OpenAI's model name, use default
        model_name = None if model in ("whisper-1", "whisper-large-v3") else model

        try:
            manager = registry.get_manager(model_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        # Read audio data
        audio_data = await file.read()

        if not audio_data:
            raise HTTPException(status_code=400, detail="Empty audio file")

        # Record metrics
        actual_model = manager.config.model_name
        metrics.record_transcription_start(actual_model)

        start_time = time.time()
        try:
            result = await manager.transcribe(
                audio_data,
                language=language,
                task=task,
                initial_prompt=prompt,
                temperature=temperature,
            )

            duration = time.time() - start_time
            metrics.record_transcription_complete(
                actual_model,
                duration,
                result.duration,
                success=True,
            )

        except Exception as e:
            duration = time.time() - start_time
            metrics.record_transcription_complete(
                actual_model,
                duration,
                0.0,
                success=False,
            )
            logger.exception("Transcription failed")
            raise HTTPException(status_code=500, detail=str(e)) from e

        # Format response
        if response_format == "text":
            return PlainTextResponse(content=result.text)

        if response_format == "srt":
            srt_content = _format_srt(result.segments)
            return PlainTextResponse(content=srt_content, media_type="text/plain")

        if response_format == "vtt":
            vtt_content = _format_vtt(result.segments)
            return PlainTextResponse(content=vtt_content, media_type="text/vtt")

        if response_format == "verbose_json":
            return VerboseTranscriptionResponse(
                task=task,
                language=result.language,
                duration=result.duration,
                text=result.text,
                segments=result.segments,
            )

        # Default is json format
        return TranscriptionResponse(text=result.text)

    def _format_srt(segments: list[dict[str, Any]]) -> str:
        """Format segments as SRT subtitles."""
        lines = []
        for i, seg in enumerate(segments, 1):
            start = _format_timestamp(seg["start"], always_include_hours=True)
            end = _format_timestamp(seg["end"], always_include_hours=True)
            text = seg["text"].strip()
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        return "\n".join(lines)

    def _format_vtt(segments: list[dict[str, Any]]) -> str:
        """Format segments as WebVTT subtitles."""
        lines = ["WEBVTT", ""]
        for seg in segments:
            start = _format_vtt_timestamp(seg["start"])
            end = _format_vtt_timestamp(seg["end"])
            text = seg["text"].strip()
            lines.append(f"{start} --> {end}\n{text}\n")
        return "\n".join(lines)

    # --- WebSocket Streaming Endpoint ---

    @app.websocket("/v1/audio/transcriptions/stream")
    async def stream_transcription(  # noqa: PLR0915
        websocket: WebSocket,
        model: Annotated[str | None, Query(description="Model to use")] = None,
        language: Annotated[str | None, Query(description="Language code")] = None,
    ) -> None:
        """WebSocket endpoint for streaming transcription.

        Protocol:
        - Client sends binary audio chunks (16kHz, 16-bit, mono PCM)
        - Client sends b"EOS" to signal end of audio
        - Server sends JSON messages with transcription results

        Message format from server:
        {"type": "partial", "text": "...", "is_final": false}
        {"type": "final", "text": "...", "is_final": true, "segments": [...]}
        {"type": "error", "message": "..."}
        """
        await websocket.accept()

        try:
            manager = registry.get_manager(model)
        except ValueError as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
            return

        # Collect audio data
        audio_buffer = io.BytesIO()
        wav_file: wave.Wave_write | None = None

        try:
            while True:
                data = await websocket.receive_bytes()

                # Check for end of stream (EOS marker)
                eos_marker = b"EOS"
                eos_len = len(eos_marker)
                if data == eos_marker or data[-eos_len:] == eos_marker:
                    # Write remaining data before EOS marker if present
                    if (
                        data[-eos_len:] == eos_marker
                        and len(data) > eos_len
                        and wav_file is not None
                    ):
                        wav_file.writeframes(data[:-eos_len])
                    break

                # Initialize WAV file on first chunk
                if wav_file is None:
                    wav_file = wave.open(audio_buffer, "wb")  # noqa: SIM115
                    wav_file.setnchannels(constants.AUDIO_CHANNELS)
                    wav_file.setsampwidth(constants.AUDIO_FORMAT_WIDTH)
                    wav_file.setframerate(constants.AUDIO_RATE)

                wav_file.writeframes(data)

            # Close WAV file
            if wav_file is not None:
                wav_file.close()

            # Get audio data
            audio_buffer.seek(0)
            audio_data = audio_buffer.read()

            if not audio_data:
                await websocket.send_json({"type": "error", "message": "No audio received"})
                await websocket.close()
                return

            # Transcribe
            actual_model = manager.config.model_name
            metrics.record_transcription_start(actual_model)
            start_time = time.time()

            try:
                result = await manager.transcribe(
                    audio_data,
                    language=language,
                    task="transcribe",
                )

                duration = time.time() - start_time
                metrics.record_transcription_complete(
                    actual_model,
                    duration,
                    result.duration,
                    success=True,
                )

                await websocket.send_json(
                    {
                        "type": "final",
                        "text": result.text,
                        "is_final": True,
                        "language": result.language,
                        "duration": result.duration,
                        "segments": result.segments,
                    },
                )

            except Exception as e:
                duration = time.time() - start_time
                metrics.record_transcription_complete(
                    actual_model,
                    duration,
                    0.0,
                    success=False,
                )
                await websocket.send_json({"type": "error", "message": str(e)})

        except Exception as e:
            logger.exception("WebSocket error")
            with contextlib.suppress(Exception):
                await websocket.send_json({"type": "error", "message": str(e)})

        finally:
            with contextlib.suppress(Exception):
                await websocket.close()

    return app
