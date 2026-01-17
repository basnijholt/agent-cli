"""FastAPI application for TTS server with OpenAI-compatible API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_cli import constants
from agent_cli.server.common import configure_app, create_lifespan
from agent_cli.server.tts.backends.base import InvalidTextError

if TYPE_CHECKING:
    from agent_cli.server.tts.model_registry import TTSModelRegistry

logger = logging.getLogger(__name__)

# OpenAI voice to Piper model mapping
OPENAI_VOICE_MAP = {
    "alloy": "en_US-lessac-medium",
    "echo": "en_US-ryan-high",
    "fable": "en_GB-alan-medium",
    "onyx": "en_US-joe-medium",
    "nova": "en_US-amy-medium",
    "shimmer": "en_US-kathleen-low",
}


# --- Pydantic Models ---


class ModelStatusResponse(BaseModel):
    """Status of a single model."""

    model_config = {"from_attributes": True}

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


class VoiceInfo(BaseModel):
    """Information about an available voice."""

    voice_id: str
    name: str
    description: str | None = None


class VoicesResponse(BaseModel):
    """Response listing available voices."""

    voices: list[VoiceInfo]


# --- App Factory ---


def create_app(
    registry: TTSModelRegistry,
    *,
    enable_wyoming: bool = True,
    wyoming_uri: str = "tcp://0.0.0.0:10400",
    background_preload: bool = False,
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        registry: The model registry to use.
        enable_wyoming: Whether to start Wyoming server.
        wyoming_uri: URI for Wyoming server.
        background_preload: Whether to preload models in the background at startup.

    Returns:
        Configured FastAPI application.

    """
    lifespan = create_lifespan(
        registry,
        wyoming_handler_module="agent_cli.server.tts.wyoming_handler",
        enable_wyoming=enable_wyoming,
        wyoming_uri=wyoming_uri,
        background_preload=background_preload,
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
        return HealthResponse(
            status="healthy",
            models=[ModelStatusResponse.model_validate(s) for s in registry.list_status()],
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

    @app.get("/v1/voices", response_model=VoicesResponse)
    async def list_voices() -> VoicesResponse:
        """List available voices (OpenAI voice names mapped to Piper models)."""
        voices = [
            VoiceInfo(
                voice_id=voice_id,
                name=voice_id,
                description=f"Maps to Piper model: {piper_model}",
            )
            for voice_id, piper_model in OPENAI_VOICE_MAP.items()
        ]
        return VoicesResponse(voices=voices)

    # --- OpenAI-Compatible TTS Endpoint ---

    @app.post("/v1/audio/speech")
    async def synthesize_speech(
        input: Annotated[str, Form(description="Text to synthesize")],  # noqa: A002
        model: Annotated[str, Form(description="Model to use")] = "tts-1",
        voice: Annotated[str, Form(description="Voice to use")] = "alloy",
        response_format: Annotated[
            str,
            Form(description="Audio format: wav, mp3, pcm"),
        ] = "wav",
        speed: Annotated[float, Form(description="Speed (0.25 to 4.0)")] = 1.0,
    ) -> StreamingResponse:
        """OpenAI-compatible text-to-speech endpoint.

        Args:
            input: Text to synthesize.
            model: Model to use (tts-1, tts-1-hd, or a Piper model name).
            voice: Voice name (alloy, echo, fable, onyx, nova, shimmer).
            response_format: Output format (wav, mp3, pcm).
            speed: Speed multiplier (0.25 to 4.0).

        Returns:
            Audio stream in the requested format.

        """
        # Resolve model name - "tts-1" and "tts-1-hd" are OpenAI's model names
        model_name = None if model in ("tts-1", "tts-1-hd") else model

        try:
            manager = registry.get_manager(model_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        if not input or not input.strip():
            raise HTTPException(status_code=400, detail="Input text cannot be empty")

        # Clamp speed to valid range
        speed = max(0.25, min(4.0, speed))

        try:
            result = await manager.synthesize(
                input,
                voice=voice,
                speed=speed,
            )
        except InvalidTextError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("Synthesis failed")
            raise HTTPException(status_code=500, detail=str(e)) from e

        # Format response based on requested format
        if response_format == "pcm":
            # Return raw PCM data (skip WAV header)
            pcm_data = (
                result.audio[constants.WAV_HEADER_SIZE :]
                if len(result.audio) > constants.WAV_HEADER_SIZE
                else result.audio
            )
            return StreamingResponse(
                iter([pcm_data]),
                media_type="audio/pcm",
                headers={
                    "X-Sample-Rate": str(result.sample_rate),
                    "X-Sample-Width": str(result.sample_width),
                    "X-Channels": str(result.channels),
                },
            )

        if response_format == "mp3":
            # MP3 encoding would require additional dependencies
            # For now, return WAV with a warning header
            logger.warning("MP3 format requested but not supported, returning WAV")
            return StreamingResponse(
                iter([result.audio]),
                media_type="audio/wav",
                headers={
                    "X-Warning": "MP3 not supported, returning WAV",
                },
            )

        # Default is WAV format
        return StreamingResponse(
            iter([result.audio]),
            media_type="audio/wav",
        )

    # --- Alternative endpoint accepting JSON body ---

    @app.post("/v1/audio/speech/json")
    async def synthesize_speech_json(
        request: dict[str, Any],
    ) -> StreamingResponse:
        """Alternative TTS endpoint accepting JSON body.

        This is for clients that prefer JSON over form data.
        """
        return await synthesize_speech(
            input=request.get("input", ""),
            model=request.get("model", "tts-1"),
            voice=request.get("voice", "alloy"),
            response_format=request.get("response_format", "wav"),
            speed=request.get("speed", 1.0),
        )

    return app
