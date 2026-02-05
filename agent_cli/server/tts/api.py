"""FastAPI application for TTS server with OpenAI-compatible API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_cli import constants
from agent_cli.core.audio_format import check_ffmpeg_available, convert_to_mp3
from agent_cli.server.common import configure_app, create_lifespan
from agent_cli.server.tts.backends.base import InvalidTextError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from agent_cli.server.tts.model_registry import TTSModelRegistry

logger = logging.getLogger(__name__)


def _format_audio_response(
    audio: bytes,
    response_format: str,
    sample_rate: int,
    sample_width: int,
    channels: int,
) -> StreamingResponse:
    """Format audio data as a streaming response."""
    if response_format == "wav":
        return StreamingResponse(iter([audio]), media_type="audio/wav")

    if response_format == "pcm":
        pcm_data = (
            audio[constants.WAV_HEADER_SIZE :] if len(audio) > constants.WAV_HEADER_SIZE else audio
        )
        return StreamingResponse(
            iter([pcm_data]),
            media_type="audio/pcm",
            headers={
                "X-Sample-Rate": str(sample_rate),
                "X-Sample-Width": str(sample_width),
                "X-Channels": str(channels),
            },
        )

    if response_format == "mp3":
        if not check_ffmpeg_available():
            raise HTTPException(
                status_code=422,
                detail="MP3 format requires ffmpeg to be installed",
            )
        try:
            mp3_data = convert_to_mp3(audio, input_format="wav")
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return StreamingResponse(iter([mp3_data]), media_type="audio/mpeg")

    # Unreachable due to early validation
    msg = f"Unsupported response_format: {response_format}"
    raise HTTPException(status_code=422, detail=msg)  # pragma: no cover


# --- Pydantic Models ---


class ModelStatusResponse(BaseModel):
    """Status of a single model."""

    name: str
    loaded: bool
    device: str | None
    ttl_seconds: int
    ttl_remaining: float | None
    active_requests: int
    # Stats
    load_count: int
    unload_count: int
    total_requests: int
    total_characters: int
    total_audio_seconds: float
    total_synthesis_seconds: float
    last_load_time: float | None
    last_request_time: float | None
    load_duration_seconds: float | None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    models: list[ModelStatusResponse]


class UnloadResponse(BaseModel):
    """Response from model unload request."""

    status: str
    model: str
    was_loaded: bool


class SpeechRequest(BaseModel):
    """Request body for JSON speech synthesis endpoint."""

    input: str
    model: str = "tts-1"
    voice: str = "alloy"
    response_format: Literal["mp3", "wav", "pcm"] = "mp3"
    speed: float = 1.0
    stream_format: Literal["audio"] | None = None


class VoiceInfo(BaseModel):
    """Information about an available voice."""

    voice_id: str
    name: str
    description: str
    preview_url: str | None = None
    labels: dict[str, str] | None = None


class VoicesResponse(BaseModel):
    """Response containing available voices."""

    voices: list[VoiceInfo]


# --- App Factory ---


def create_app(
    registry: TTSModelRegistry,
    *,
    enable_wyoming: bool = True,
    wyoming_uri: str = "tcp://0.0.0.0:10200",
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        registry: The model registry to use.
        enable_wyoming: Whether to start Wyoming server.
        wyoming_uri: URI for Wyoming server.

    Returns:
        Configured FastAPI application.

    """
    lifespan = create_lifespan(
        registry,
        wyoming_handler_module="agent_cli.server.tts.wyoming_handler",
        enable_wyoming=enable_wyoming,
        wyoming_uri=wyoming_uri,
    )

    app = FastAPI(
        title="TTS Server",
        description="OpenAI-compatible TTS server with TTL-based model unloading",
        version="1.0.0",
        lifespan=lifespan,
    )

    configure_app(app)

    # --- Health & Status Endpoints ---

    @app.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Health check endpoint."""
        models = [
            ModelStatusResponse(
                name=s.name,
                loaded=s.loaded,
                device=s.device,
                ttl_seconds=s.ttl_seconds,
                ttl_remaining=s.ttl_remaining,
                active_requests=s.active_requests,
                load_count=s.load_count,
                unload_count=s.unload_count,
                total_requests=s.total_requests,
                total_characters=int(s.extra.get("total_characters", 0.0)),
                total_audio_seconds=s.total_audio_seconds,
                total_synthesis_seconds=s.extra.get("total_synthesis_seconds", 0.0),
                last_load_time=s.last_load_time,
                last_request_time=s.last_request_time,
                load_duration_seconds=s.load_duration_seconds,
            )
            for s in registry.list_status()
        ]
        return HealthResponse(status="healthy", models=models)

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

    @app.get("/v1/voices", response_model=VoicesResponse)
    async def list_voices() -> VoicesResponse:
        """List available voices (models).

        For Piper TTS, each model IS a voice. This endpoint returns
        the list of registered models as available voices.
        """
        voices = [
            VoiceInfo(
                voice_id=s.name,
                name=s.name,
                description=f"Piper TTS voice: {s.name}",
                labels={"language": s.name.split("_")[0] if "_" in s.name else "en"},
            )
            for s in registry.list_status()
        ]
        return VoicesResponse(voices=voices)

    # --- OpenAI-Compatible TTS Endpoint ---

    async def _synthesize(
        input_text: str,
        model: str,
        voice: str,
        response_format: str,
        speed: float,
        stream_format: str | None,
    ) -> StreamingResponse:
        """Core synthesis logic shared by JSON and form endpoints."""
        # Resolve model name - "tts-1" and "tts-1-hd" are OpenAI's model names
        model_name = None if model in ("tts-1", "tts-1-hd") else model

        try:
            manager = registry.get_manager(model_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        if not input_text.strip():
            raise HTTPException(status_code=400, detail="Input text cannot be empty")

        # Clamp speed to valid range
        speed = max(0.25, min(4.0, speed))

        # Handle streaming mode (OpenAI uses stream_format=audio with response_format=pcm)
        if stream_format is not None:
            if stream_format != "audio":
                raise HTTPException(
                    status_code=422,
                    detail="Only 'audio' stream_format is supported",
                )
            if response_format != "pcm":
                raise HTTPException(
                    status_code=422,
                    detail="Streaming requires response_format=pcm",
                )
            if not manager.supports_streaming:
                raise HTTPException(
                    status_code=422,
                    detail="This model does not support streaming synthesis",
                )

            async def generate_audio() -> AsyncIterator[bytes]:
                async for chunk in manager.synthesize_stream(
                    input_text,
                    voice=voice,
                    speed=speed,
                ):
                    yield chunk

            return StreamingResponse(
                generate_audio(),
                media_type="audio/pcm",
                headers={
                    "X-Sample-Rate": str(constants.KOKORO_DEFAULT_SAMPLE_RATE),
                    "X-Sample-Width": "2",
                    "X-Channels": "1",
                },
            )

        # Non-streaming mode: validate format and synthesize complete audio
        valid_formats = ("wav", "pcm", "mp3")
        if response_format not in valid_formats:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported response_format: {response_format}. Supported: {', '.join(valid_formats)}",
            )

        try:
            result = await manager.synthesize(
                input_text,
                voice=voice,
                speed=speed,
            )
        except InvalidTextError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("Synthesis failed")
            raise HTTPException(status_code=500, detail=str(e)) from e

        return _format_audio_response(
            result.audio,
            response_format,
            result.sample_rate,
            result.sample_width,
            result.channels,
        )

    @app.post("/v1/audio/speech")
    async def synthesize_speech(request: SpeechRequest) -> StreamingResponse:
        """OpenAI-compatible text-to-speech endpoint.

        Accepts JSON body with input, model, voice, response_format, speed,
        and optional stream_format parameters.
        """
        return await _synthesize(
            input_text=request.input,
            model=request.model,
            voice=request.voice,
            response_format=request.response_format,
            speed=request.speed,
            stream_format=request.stream_format,
        )

    return app
