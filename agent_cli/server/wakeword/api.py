"""FastAPI application for wakeword server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from agent_cli.server.common import configure_app, create_lifespan

if TYPE_CHECKING:
    from agent_cli.server.wakeword.model_registry import WakewordModelRegistry

logger = logging.getLogger(__name__)


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
    total_detections: int
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


class WakeModelInfo(BaseModel):
    """Information about an available wake word model."""

    name: str
    phrase: str
    languages: list[str]
    is_builtin: bool


class ModelsResponse(BaseModel):
    """Response containing available models."""

    models: list[WakeModelInfo]


class DetectionEvent(BaseModel):
    """Wake word detection event."""

    name: str
    timestamp: int
    probability: float


# --- App Factory ---


def create_app(
    registry: WakewordModelRegistry,
    *,
    enable_wyoming: bool = True,
    wyoming_uri: str = "tcp://0.0.0.0:10400",
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
        wyoming_handler_module="agent_cli.server.wakeword.wyoming_handler",
        enable_wyoming=enable_wyoming,
        wyoming_uri=wyoming_uri,
    )

    app = FastAPI(
        title="Wakeword Server",
        description="Wake word detection server with TTL-based model unloading",
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
                total_detections=int(s.extra.get("total_detections", 0.0)),
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

    @app.get("/v1/models", response_model=ModelsResponse)
    async def list_models() -> ModelsResponse:
        """List available wake word models."""
        models: list[WakeModelInfo] = []
        seen_models: set[str] = set()

        for status in registry.list_status():
            manager = registry.get_manager(status.name)
            if manager.is_loaded:
                for model_info in manager.get_available_models():
                    if model_info.name not in seen_models:
                        seen_models.add(model_info.name)
                        models.append(
                            WakeModelInfo(
                                name=model_info.name,
                                phrase=model_info.phrase,
                                languages=model_info.languages,
                                is_builtin=model_info.is_builtin,
                            ),
                        )

        # Add registered but not loaded models
        for status in registry.list_status():
            if status.name not in seen_models:
                seen_models.add(status.name)
                phrase = " ".join(
                    w.capitalize() for w in status.name.replace("_", " ").replace("-", " ").split()
                )
                models.append(
                    WakeModelInfo(
                        name=status.name,
                        phrase=phrase,
                        languages=["en"],
                        is_builtin=True,
                    ),
                )

        return ModelsResponse(models=models)

    # --- WebSocket Endpoint for Real-time Detection ---

    @app.websocket("/v1/detect")
    async def websocket_detect(
        websocket: WebSocket,
        model: str | None = None,
    ) -> None:
        """WebSocket endpoint for real-time wake word detection.

        Connect and send raw PCM audio chunks (16-bit, 16kHz, mono).
        Receive JSON detection events when wake words are detected.

        Query params:
            model: Wake word model to use (default: server default)
        """
        await websocket.accept()

        try:
            manager = registry.get_manager(model)
        except ValueError as e:
            await websocket.close(code=1008, reason=str(e))
            return

        # Reset detector state
        manager.reset()

        try:
            while True:
                # Receive raw PCM audio bytes
                audio_chunk = await websocket.receive_bytes()

                # Process audio
                detections = await manager.process_audio(audio_chunk)

                # Send detection events
                for detection in detections:
                    await websocket.send_json(
                        DetectionEvent(
                            name=detection.name,
                            timestamp=detection.timestamp,
                            probability=detection.probability,
                        ).model_dump(),
                    )

        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected")
        except Exception as e:
            logger.exception("WebSocket error")
            await websocket.close(code=1011, reason=str(e))

    return app
