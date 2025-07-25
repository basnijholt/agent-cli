"""FastAPI web service for Agent CLI transcription."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from agent_cli import config, opts
from agent_cli.agents.transcribe import AGENT_INSTRUCTIONS, INSTRUCTION, SYSTEM_PROMPT
from agent_cli.services import asr
from agent_cli.services.llm import process_and_update_clipboard

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Agent CLI Transcription API",
    description="Web service for audio transcription and text cleanup",
    version="1.0.0",
)


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Any:  # type: ignore[no-untyped-def]  # noqa: ANN001
    """Log basic request information."""
    client_ip = request.client.host if request.client else "unknown"
    logger.info("%s %s from %s", request.method, request.url.path, client_ip)

    response = await call_next(request)

    if response.status_code >= 400:  # noqa: PLR2004
        logger.warning(
            "Request failed: %s %s → %d",
            request.method,
            request.url.path,
            response.status_code,
        )

    return response


class TranscriptionResponse(BaseModel):
    """Response model for transcription endpoint."""

    raw_transcript: str
    cleaned_transcript: str | None = None
    success: bool
    error: str | None = None


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    version: str


class TranscriptionRequest(BaseModel):
    """Request model for transcription endpoint."""

    cleanup: bool = True
    extra_instructions: str | None = None


async def parse_transcription_form(
    cleanup: Annotated[str | bool, Form()] = True,
    extra_instructions: Annotated[str | None, Form()] = None,
) -> TranscriptionRequest:
    """Parse form data into TranscriptionRequest model."""
    return TranscriptionRequest(cleanup=cleanup, extra_instructions=extra_instructions)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


async def _transcribe_with_provider(
    audio_data: bytes,
    provider_cfg: config.ProviderSelection,
    wyoming_asr_cfg: config.WyomingASR,
    openai_asr_cfg: config.OpenAIASR,
    logger: logging.Logger,
) -> str:
    """Transcribe audio using the configured provider."""
    transcriber = asr.create_recorded_audio_transcriber(provider_cfg)

    if provider_cfg.asr_provider == "local":
        return await transcriber(
            audio_data=audio_data,
            wyoming_asr_cfg=wyoming_asr_cfg,
            logger=logger,
        )
    if provider_cfg.asr_provider == "openai":
        return await transcriber(
            audio_data=audio_data,
            openai_asr_cfg=openai_asr_cfg,
            logger=logger,
        )
    msg = f"Unsupported ASR provider: {provider_cfg.asr_provider}"
    raise ValueError(msg)


async def _extract_audio_file_from_request(
    request: Request,
    audio: UploadFile | None,
) -> UploadFile:
    """Extract and validate audio file from request."""
    # First try the standard 'audio' parameter
    if audio is not None:
        return audio

    # iOS Shortcuts may use a different field name, scan form for audio files
    logger.info("No 'audio' parameter found, scanning form fields for audio files")
    form_data = await request.form()

    for key, value in form_data.items():
        if (
            hasattr(value, "filename")
            and hasattr(value, "content_type")
            and (
                (value.content_type and value.content_type.startswith("audio/"))
                or (
                    value.filename
                    and value.filename.lower().endswith(
                        (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"),
                    )
                )
            )
        ):
            logger.info("Found audio file in field '%s': %s", key, value.filename)
            return value

    # No audio file found anywhere
    raise HTTPException(
        status_code=422,
        detail="No audio file provided. Ensure the form field is named 'audio' and type is 'File'.",
    )


def _validate_audio_file(audio: UploadFile) -> str:
    """Validate audio file and return file extension."""
    if not audio or not audio.filename:
        logger.error("No filename provided in request")
        raise HTTPException(status_code=400, detail="No filename provided")

    valid_extensions = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
    file_ext = Path(audio.filename).suffix.lower()

    if file_ext not in valid_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format: {file_ext}. Supported: {', '.join(valid_extensions)}",
        )

    return file_ext


def _load_transcription_configs() -> tuple[
    config.ProviderSelection,
    config.WyomingASR,
    config.OpenAIASR,
    config.Ollama,
    config.OpenAILLM,
    config.GeminiLLM,
    dict[str, Any],
]:
    """Load and create all required configuration objects."""
    loaded_config = config.load_config()
    wildcard_config = loaded_config.get("defaults", {})
    command_config = loaded_config.get("transcribe", {})
    defaults = {**wildcard_config, **command_config}

    provider_cfg = config.ProviderSelection(
        asr_provider=defaults.get("asr_provider", opts.ASR_PROVIDER.default),  # type: ignore[attr-defined]
        llm_provider=defaults.get("llm_provider", opts.LLM_PROVIDER.default),  # type: ignore[attr-defined]
        tts_provider=opts.TTS_PROVIDER.default,  # type: ignore[attr-defined]
    )
    wyoming_asr_cfg = config.WyomingASR(
        asr_wyoming_ip=defaults.get("asr_wyoming_ip", opts.ASR_WYOMING_IP.default),  # type: ignore[attr-defined]
        asr_wyoming_port=defaults.get("asr_wyoming_port", opts.ASR_WYOMING_PORT.default),  # type: ignore[attr-defined]
    )
    openai_asr_cfg = config.OpenAIASR(
        asr_openai_model=defaults.get("asr_openai_model", opts.ASR_OPENAI_MODEL.default),  # type: ignore[attr-defined]
        openai_api_key=defaults.get("openai_api_key", opts.OPENAI_API_KEY.default),  # type: ignore[attr-defined,union-attr]
    )
    ollama_cfg = config.Ollama(
        llm_ollama_model=defaults.get("llm_ollama_model", opts.LLM_OLLAMA_MODEL.default),  # type: ignore[attr-defined]
        llm_ollama_host=defaults.get("llm_ollama_host", opts.LLM_OLLAMA_HOST.default),  # type: ignore[attr-defined]
    )
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=defaults.get("llm_openai_model", opts.LLM_OPENAI_MODEL.default),  # type: ignore[attr-defined]
        openai_api_key=defaults.get("openai_api_key", opts.OPENAI_API_KEY.default),  # type: ignore[attr-defined,union-attr]
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model=defaults.get("llm_gemini_model", opts.LLM_GEMINI_MODEL.default),  # type: ignore[attr-defined]
        gemini_api_key=defaults.get("gemini_api_key", opts.GEMINI_API_KEY.default),  # type: ignore[attr-defined,union-attr]
    )

    return (
        provider_cfg,
        wyoming_asr_cfg,
        openai_asr_cfg,
        ollama_cfg,
        openai_llm_cfg,
        gemini_llm_cfg,
        defaults,
    )


def _convert_audio_for_local_asr(audio_data: bytes, filename: str) -> bytes:
    """Convert audio to Wyoming format if needed for local ASR."""
    from agent_cli.core.audio_format import convert_audio_to_wyoming_format  # noqa: PLC0415

    logger.info("Converting %s audio to Wyoming format", filename)
    converted_data = convert_audio_to_wyoming_format(audio_data, filename)
    logger.info("Audio conversion successful")
    return converted_data


async def _process_transcript_cleanup(
    raw_transcript: str,
    cleanup: bool,
    extra_instructions: str | None,
    defaults: dict[str, Any],
    provider_cfg: config.ProviderSelection,
    ollama_cfg: config.Ollama,
    openai_llm_cfg: config.OpenAILLM,
    gemini_llm_cfg: config.GeminiLLM,
) -> str | None:
    """Process transcript cleanup with LLM if requested."""
    if not cleanup:
        return None

    instructions = AGENT_INSTRUCTIONS
    config_extra = defaults.get("extra_instructions", "")
    if config_extra:
        instructions += f"\n\n{config_extra}"
    if extra_instructions:
        instructions += f"\n\n{extra_instructions}"

    return await process_and_update_clipboard(
        system_prompt=SYSTEM_PROMPT,
        agent_instructions=instructions,
        provider_cfg=provider_cfg,
        ollama_cfg=ollama_cfg,
        openai_cfg=openai_llm_cfg,
        gemini_cfg=gemini_llm_cfg,
        logger=logger,
        original_text=raw_transcript,
        instruction=INSTRUCTION,
        clipboard=False,  # Don't copy to clipboard in web service
        quiet=True,
        live=None,
    )


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    request: Request,
    form_data: Annotated[TranscriptionRequest, Depends(parse_transcription_form)],
    audio: Annotated[UploadFile | None, File()] = None,
) -> TranscriptionResponse:
    """Transcribe audio file and optionally clean up the text.

    Args:
        request: FastAPI request object
        audio: Audio file (wav, mp3, m4a, etc.)
        form_data: Form data with cleanup and extra_instructions

    Returns:
        TranscriptionResponse with raw and cleaned transcripts

    """
    try:
        # Extract and validate audio file
        audio = await _extract_audio_file_from_request(request, audio)
        file_ext = _validate_audio_file(audio)

        # Extract form data (Pydantic handles string->bool conversion automatically)
        cleanup = form_data.cleanup
        extra_instructions = form_data.extra_instructions

        # Load all configurations
        (
            provider_cfg,
            wyoming_asr_cfg,
            openai_asr_cfg,
            ollama_cfg,
            openai_llm_cfg,
            gemini_llm_cfg,
            defaults,
        ) = _load_transcription_configs()

        # Save uploaded file temporarily and process
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as temp_file:
            content = await audio.read()
            temp_file.write(content)
            temp_file_path = Path(temp_file.name)

        # Read audio file as bytes
        audio_data = temp_file_path.read_bytes()

        # Convert audio to Wyoming format if using local ASR
        if provider_cfg.asr_provider == "local":
            audio_data = _convert_audio_for_local_asr(audio_data, audio.filename)

        # Transcribe audio using the configured provider
        raw_transcript = await _transcribe_with_provider(
            audio_data,
            provider_cfg,
            wyoming_asr_cfg,
            openai_asr_cfg,
            logger,
        )

        if not raw_transcript:
            return TranscriptionResponse(
                raw_transcript="",
                success=False,
                error="No transcript generated from audio",
            )

        # Process transcript cleanup if requested
        cleaned_transcript = await _process_transcript_cleanup(
            raw_transcript,
            cleanup,
            extra_instructions,
            defaults,
            provider_cfg,
            ollama_cfg,
            openai_llm_cfg,
            gemini_llm_cfg,
        )

        return TranscriptionResponse(
            raw_transcript=raw_transcript,
            cleaned_transcript=cleaned_transcript,
            success=True,
        )

    except HTTPException:
        # Re-raise HTTPExceptions so FastAPI handles them properly
        raise
    except Exception as e:
        logger.exception(
            "Error during transcription - Exception type: %s, args: %s",
            type(e).__name__,
            e.args,
        )
        return TranscriptionResponse(raw_transcript="", success=False, error=str(e))
    finally:
        # Clean up temporary file
        if "temp_file_path" in locals():
            temp_file_path.unlink(missing_ok=True)
