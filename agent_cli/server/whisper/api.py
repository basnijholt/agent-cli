"""FastAPI application for Whisper ASR server with OpenAI-compatible API."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from agent_cli.server.common import configure_app, create_lifespan
from agent_cli.server.whisper.backends.base import InvalidAudioError
from agent_cli.services import pcm_to_wav

if TYPE_CHECKING:
    from agent_cli.core.vad import VoiceActivityDetector
    from agent_cli.server.whisper.model_registry import WhisperModelRegistry

logger = logging.getLogger(__name__)

_EOS_MARKER = b"EOS"


def _parse_eos(data: bytes) -> tuple[bytes, bool]:
    """Parse data for EOS marker, returning (audio_chunk, is_eos)."""
    if data == _EOS_MARKER:
        return b"", True
    if data.endswith(_EOS_MARKER):
        return data[: -len(_EOS_MARKER)], True
    return data, False


def _create_vad(
    threshold: float,
    silence_threshold_ms: int,
    min_speech_duration_ms: int,
) -> VoiceActivityDetector:
    """Create a VoiceActivityDetector instance.

    Raises ImportError if onnxruntime is not available.
    """
    from agent_cli.core.vad import VoiceActivityDetector  # noqa: PLC0415

    try:
        return VoiceActivityDetector(
            threshold=threshold,
            silence_threshold_ms=silence_threshold_ms,
            min_speech_duration_ms=min_speech_duration_ms,
        )
    except ImportError as e:
        msg = (
            "VAD requires onnxruntime. Install it with: "
            "`pip install agent-cli[vad]` or `uv sync --extra vad`"
        )
        raise ImportError(msg) from e


def _split_seconds(seconds: float) -> tuple[int, int, int, int]:
    """Split seconds into (hours, minutes, seconds, milliseconds)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return hours, minutes, secs, millis


def _format_timestamp(seconds: float, *, always_include_hours: bool = False) -> str:
    """Format seconds as HH:MM:SS,mmm for SRT format."""
    hours, minutes, secs, millis = _split_seconds(seconds)
    if always_include_hours or hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    return f"{minutes:02d}:{secs:02d},{millis:03d}"


def _format_vtt_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm for VTT format."""
    hours, minutes, secs, millis = _split_seconds(seconds)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


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


# --- Pydantic Models ---


class TranscriptionResponse(BaseModel):
    """OpenAI-compatible transcription response."""

    text: str


class VerboseTranscriptionResponse(BaseModel):
    """OpenAI-compatible verbose transcription response."""

    task: Literal["transcribe", "translate"]
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
    active_requests: int
    # Stats
    load_count: int
    unload_count: int
    total_requests: int
    total_audio_seconds: float
    total_transcription_seconds: float
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


# --- App Factory ---


def create_app(  # noqa: C901, PLR0915
    registry: WhisperModelRegistry,
    *,
    enable_wyoming: bool = True,
    wyoming_uri: str = "tcp://0.0.0.0:10300",
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
        wyoming_handler_module="agent_cli.server.whisper.wyoming_handler",
        enable_wyoming=enable_wyoming,
        wyoming_uri=wyoming_uri,
    )

    app = FastAPI(
        title="Whisper ASR Server",
        description="OpenAI-compatible Whisper ASR server with TTL-based model unloading",
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
                total_audio_seconds=s.total_audio_seconds,
                total_transcription_seconds=s.extra.get("total_transcription_seconds", 0.0),
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
        response_format: Literal["json", "text", "srt", "verbose_json", "vtt"],
        temperature: float,
        task: Literal["transcribe", "translate"],
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

        try:
            result = await manager.transcribe(
                audio_data,
                source_filename=file.filename,
                language=language,
                task=task,
                initial_prompt=prompt,
                temperature=temperature,
            )
        except InvalidAudioError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
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

    # --- WebSocket Streaming Endpoint ---

    @app.websocket("/v1/audio/transcriptions/stream")
    async def stream_transcription(
        websocket: WebSocket,
        model: Annotated[str | None, Query(description="Model to use")] = None,
        language: Annotated[str | None, Query(description="Language code")] = None,
        use_vad: Annotated[
            bool,
            Query(description="Enable VAD for streaming partial results"),
        ] = True,
        vad_threshold: Annotated[
            float,
            Query(description="Speech detection threshold (0.0-1.0)", ge=0.0, le=1.0),
        ] = 0.3,
        vad_silence_ms: Annotated[
            int,
            Query(description="Silence duration (ms) to end speech segment", ge=100, le=5000),
        ] = 1000,
        vad_min_speech_ms: Annotated[
            int,
            Query(
                description="Minimum speech duration (ms) to trigger transcription",
                ge=50,
                le=2000,
            ),
        ] = 250,
    ) -> None:
        """WebSocket endpoint for streaming transcription with optional VAD.

        Protocol:
        - Client sends binary audio chunks (16kHz, 16-bit, mono PCM)
        - Client sends b"EOS" to signal end of audio
        - Server sends JSON messages with transcription results

        When use_vad=True (default):
        - Partial transcriptions are sent as speech segments complete
        - Final message contains combined text from all segments

        Message format from server:
        {"type": "partial", "text": "...", "is_final": false, "language": "..."}
        {"type": "final", "text": "...", "is_final": true, "language": "...", ...}
        {"type": "error", "message": "..."}
        """
        await websocket.accept()

        try:
            # Match OpenAI model aliases to the default model, like REST endpoints.
            resolved_model = None if model in ("whisper-1", "whisper-large-v3") else model
            manager = registry.get_manager(resolved_model)
        except ValueError as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
            return

        # Initialize VAD if requested
        vad = None
        if use_vad:
            try:
                vad = _create_vad(
                    threshold=vad_threshold,
                    silence_threshold_ms=vad_silence_ms,
                    min_speech_duration_ms=vad_min_speech_ms,
                )
            except ImportError as e:
                await websocket.send_json({"type": "error", "message": str(e)})
                await websocket.close()
                return

        try:
            if vad is not None:
                # VAD-enabled streaming mode
                await _stream_with_vad(websocket, manager, vad, language)
            else:
                # Legacy buffered mode (no VAD)
                await _stream_buffered(websocket, manager, language)
        except Exception as e:
            logger.exception("WebSocket error")
            with contextlib.suppress(Exception):
                await websocket.send_json({"type": "error", "message": str(e)})
        finally:
            with contextlib.suppress(Exception):
                await websocket.close()

    async def _stream_with_vad(
        websocket: WebSocket,
        manager: Any,
        vad: VoiceActivityDetector,
        language: str | None,
    ) -> None:
        """Handle streaming transcription with VAD-based segmentation."""
        all_segments_text: list[str] = []
        total_duration: float = 0.0
        final_language: str | None = None

        async def process_segment(segment: bytes) -> None:
            """Transcribe segment and send partial result."""
            nonlocal final_language, total_duration
            result = await _transcribe_segment(manager, segment, language)
            if result and result.text.strip():
                all_segments_text.append(result.text.strip())
                final_language = result.language
                total_duration += result.duration
                await websocket.send_json(
                    {
                        "type": "partial",
                        "text": result.text.strip(),
                        "is_final": False,
                        "language": result.language,
                    },
                )

        while True:
            data = await websocket.receive_bytes()
            audio_chunk, is_eos = _parse_eos(data)

            # Process audio chunk through VAD
            if audio_chunk:
                _is_speaking, segment = vad.process_chunk(audio_chunk)
                if segment:
                    await process_segment(segment)

            if is_eos:
                # Flush any remaining audio in VAD buffer
                if remaining := vad.flush():
                    await process_segment(remaining)
                break

        # Send final combined result
        final_text = " ".join(all_segments_text)
        await websocket.send_json(
            {
                "type": "final",
                "text": final_text,
                "is_final": True,
                "language": final_language,
                "duration": total_duration,
            },
        )

    async def _stream_buffered(
        websocket: WebSocket,
        manager: Any,
        language: str | None,
    ) -> None:
        """Handle streaming transcription with buffered mode (no VAD)."""
        pcm_chunks: list[bytes] = []

        while True:
            data = await websocket.receive_bytes()
            audio_chunk, is_eos = _parse_eos(data)
            if audio_chunk:
                pcm_chunks.append(audio_chunk)
            if is_eos:
                break

        if not pcm_chunks:
            await websocket.send_json({"type": "error", "message": "No audio received"})
            return

        # Transcribe
        audio_data = pcm_to_wav(b"".join(pcm_chunks))
        try:
            result = await manager.transcribe(
                audio_data,
                language=language,
                task="transcribe",
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
            await websocket.send_json({"type": "error", "message": str(e)})

    async def _transcribe_segment(
        manager: Any,
        segment: bytes,
        language: str | None,
    ) -> Any | None:
        """Transcribe a raw PCM audio segment."""
        try:
            return await manager.transcribe(
                pcm_to_wav(segment),
                language=language,
                task="transcribe",
            )
        except Exception:
            logger.exception("Failed to transcribe segment")
            return None

    return app
