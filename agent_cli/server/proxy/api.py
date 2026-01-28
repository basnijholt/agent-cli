"""FastAPI web service for Agent CLI transcription."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from agent_cli import config, opts
from agent_cli.agents.transcribe import (
    AGENT_INSTRUCTIONS,
    INSTRUCTION,
    SYSTEM_PROMPT,
    _build_context_payload,
)
from agent_cli.core.audio_format import (
    VALID_EXTENSIONS,
    convert_audio_to_wyoming_format,
    is_valid_audio_file,
)
from agent_cli.core.transcription_logger import TranscriptionLogger, get_default_logger
from agent_cli.server.common import log_requests_middleware
from agent_cli.services import asr
from agent_cli.services.llm import process_and_update_clipboard

if TYPE_CHECKING:
    from typer.models import OptionInfo

# Configure logging
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

app = FastAPI(
    title="Agent CLI Transcription API",
    description="Web service for audio transcription and text cleanup",
    version="1.0.0",
)


@app.on_event("startup")
async def log_effective_config() -> None:
    """Log effective configuration on startup to help debug env var issues."""
    (
        provider_cfg,
        wyoming_cfg,
        openai_asr_cfg,
        gemini_asr_cfg,
        ollama_cfg,
        openai_llm_cfg,
        gemini_llm_cfg,
        _,
    ) = _load_transcription_configs()

    LOGGER.info("ASR provider: %s", provider_cfg.asr_provider)
    if provider_cfg.asr_provider == "wyoming":
        LOGGER.info("  Wyoming: %s:%d", wyoming_cfg.asr_wyoming_ip, wyoming_cfg.asr_wyoming_port)
    elif provider_cfg.asr_provider == "openai":
        LOGGER.info("  Model: %s", openai_asr_cfg.asr_openai_model)
        LOGGER.info("  Base URL: %s", openai_asr_cfg.openai_base_url or "https://api.openai.com/v1")
    elif provider_cfg.asr_provider == "gemini":
        LOGGER.info("  Model: %s", gemini_asr_cfg.asr_gemini_model)

    LOGGER.info("LLM provider: %s", provider_cfg.llm_provider)
    if provider_cfg.llm_provider == "ollama":
        LOGGER.info("  Model: %s", ollama_cfg.llm_ollama_model)
        LOGGER.info("  Host: %s", ollama_cfg.llm_ollama_host)
    elif provider_cfg.llm_provider == "openai":
        LOGGER.info("  Model: %s", openai_llm_cfg.llm_openai_model)
        LOGGER.info("  Base URL: %s", openai_llm_cfg.openai_base_url or "https://api.openai.com/v1")
    elif provider_cfg.llm_provider == "gemini":
        LOGGER.info("  Model: %s", gemini_llm_cfg.llm_gemini_model)


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Any:  # type: ignore[no-untyped-def]  # noqa: ANN001
    """Log basic request information."""
    return await log_requests_middleware(request, call_next)


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


async def _parse_transcription_form(
    cleanup: Annotated[str | bool, Form()] = True,
    extra_instructions: Annotated[str | None, Form()] = None,
) -> TranscriptionRequest:
    """Parse form data into TranscriptionRequest model."""
    cleanup_bool = cleanup.lower() in ("true", "1", "yes") if isinstance(cleanup, str) else cleanup
    return TranscriptionRequest(cleanup=cleanup_bool, extra_instructions=extra_instructions)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


async def _transcribe_with_provider(
    audio_data: bytes,
    filename: str,
    provider_cfg: config.ProviderSelection,
    wyoming_asr_cfg: config.WyomingASR,
    openai_asr_cfg: config.OpenAIASR,
    gemini_asr_cfg: config.GeminiASR,
) -> str:
    """Transcribe audio using the configured provider."""
    transcriber = asr.create_recorded_audio_transcriber(provider_cfg)
    file_suffix = Path(filename).suffix.lower() or ".wav"

    if provider_cfg.asr_provider == "wyoming":
        return await transcriber(
            audio_data=audio_data,
            wyoming_asr_cfg=wyoming_asr_cfg,
            logger=LOGGER,
        )
    if provider_cfg.asr_provider == "openai":
        return await transcriber(
            audio_data=audio_data,
            openai_asr_cfg=openai_asr_cfg,
            logger=LOGGER,
            file_suffix=file_suffix,
        )
    if provider_cfg.asr_provider == "gemini":
        return await transcriber(
            audio_data=audio_data,
            gemini_asr_cfg=gemini_asr_cfg,
            logger=LOGGER,
            file_suffix=file_suffix,
        )
    msg = f"Unsupported ASR provider: {provider_cfg.asr_provider}"
    raise NotImplementedError(msg)


async def _extract_audio_file_from_request(
    request: Request,
    audio: UploadFile | None,
) -> UploadFile:
    """Extract and validate audio file from request."""
    # First try the standard 'audio' parameter
    if audio is not None:
        return audio

    # iOS Shortcuts may use a different field name, scan form for audio files
    LOGGER.info("No 'audio' parameter found, scanning form fields for audio files")
    form_data = await request.form()

    for key, value in form_data.items():
        if is_valid_audio_file(value):
            LOGGER.info("Found audio file in field '%s': %s", key, value.filename)
            return value

    # No audio file found anywhere
    raise HTTPException(
        status_code=422,
        detail="No audio file provided. Ensure the form field is named 'audio' and type is 'File'.",
    )


def _validate_audio_file(audio: UploadFile) -> None:
    """Validate audio file and return file extension."""
    if not audio or not audio.filename:
        LOGGER.error("No filename provided in request")
        raise HTTPException(status_code=400, detail="No filename provided")

    file_ext = Path(audio.filename).suffix.lower()

    if file_ext not in VALID_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format: {file_ext}. Supported: {', '.join(VALID_EXTENSIONS)}",
        )


def _cfg(key: str, defaults: dict[str, Any], opt: OptionInfo) -> Any:
    """Get config with priority: env var > config file > option default."""
    if opt.envvar and (env_val := os.environ.get(opt.envvar)):
        return int(env_val) if isinstance(opt.default, int) else env_val
    return defaults.get(key, opt.default)


def _load_transcription_configs() -> tuple[
    config.ProviderSelection,
    config.WyomingASR,
    config.OpenAIASR,
    config.GeminiASR,
    config.Ollama,
    config.OpenAILLM,
    config.GeminiLLM,
    dict[str, Any],
]:
    """Load config objects. Priority: env var > config file > default."""
    loaded_config = config.load_config()
    wildcard_config = loaded_config.get("defaults", {})
    command_config = loaded_config.get("transcribe", {})
    defaults = {**wildcard_config, **command_config}

    provider_cfg = config.ProviderSelection(
        asr_provider=_cfg("asr_provider", defaults, opts.ASR_PROVIDER),
        llm_provider=_cfg("llm_provider", defaults, opts.LLM_PROVIDER),
        tts_provider=_cfg("tts_provider", defaults, opts.TTS_PROVIDER),
    )
    wyoming_asr_cfg = config.WyomingASR(
        asr_wyoming_ip=_cfg("asr_wyoming_ip", defaults, opts.ASR_WYOMING_IP),
        asr_wyoming_port=_cfg("asr_wyoming_port", defaults, opts.ASR_WYOMING_PORT),
    )
    openai_asr_cfg = config.OpenAIASR(
        asr_openai_model=_cfg("asr_openai_model", defaults, opts.ASR_OPENAI_MODEL),
        openai_api_key=_cfg("openai_api_key", defaults, opts.OPENAI_API_KEY),
        openai_base_url=_cfg("asr_openai_base_url", defaults, opts.ASR_OPENAI_BASE_URL),
        asr_openai_prompt=_cfg("asr_openai_prompt", defaults, opts.ASR_OPENAI_PROMPT),
    )
    gemini_asr_cfg = config.GeminiASR(
        asr_gemini_model=_cfg("asr_gemini_model", defaults, opts.ASR_GEMINI_MODEL),
        gemini_api_key=_cfg("gemini_api_key", defaults, opts.GEMINI_API_KEY),
    )
    ollama_cfg = config.Ollama(
        llm_ollama_model=_cfg("llm_ollama_model", defaults, opts.LLM_OLLAMA_MODEL),
        llm_ollama_host=_cfg("llm_ollama_host", defaults, opts.LLM_OLLAMA_HOST),
    )
    openai_llm_cfg = config.OpenAILLM(
        llm_openai_model=_cfg("llm_openai_model", defaults, opts.LLM_OPENAI_MODEL),
        openai_api_key=_cfg("openai_api_key", defaults, opts.OPENAI_API_KEY),
        openai_base_url=_cfg("openai_base_url", defaults, opts.OPENAI_BASE_URL),
    )
    gemini_llm_cfg = config.GeminiLLM(
        llm_gemini_model=_cfg("llm_gemini_model", defaults, opts.LLM_GEMINI_MODEL),
        gemini_api_key=_cfg("gemini_api_key", defaults, opts.GEMINI_API_KEY),
    )

    return (
        provider_cfg,
        wyoming_asr_cfg,
        openai_asr_cfg,
        gemini_asr_cfg,
        ollama_cfg,
        openai_llm_cfg,
        gemini_llm_cfg,
        defaults,
    )


def _convert_audio_for_local_asr(audio_data: bytes, filename: str) -> bytes:
    """Convert audio to Wyoming format if needed for local ASR."""
    LOGGER.info("Converting %s audio to Wyoming format", filename)
    converted_data = convert_audio_to_wyoming_format(audio_data, filename)
    LOGGER.info("Audio conversion successful")
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
    transcription_log: Path | None,
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

    combined_context, context_note = _build_context_payload(
        transcription_log=transcription_log,
        clipboard_snapshot=None,
    )
    if context_note:
        instructions += context_note

    return await process_and_update_clipboard(
        system_prompt=SYSTEM_PROMPT,
        agent_instructions=instructions,
        provider_cfg=provider_cfg,
        ollama_cfg=ollama_cfg,
        openai_cfg=openai_llm_cfg,
        gemini_cfg=gemini_llm_cfg,
        logger=LOGGER,
        original_text=raw_transcript,
        instruction=INSTRUCTION,
        clipboard=False,  # Don't copy to clipboard in web service
        quiet=True,
        live=None,
        context=combined_context,
    )


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    request: Request,
    form_data: Annotated[TranscriptionRequest, Depends(_parse_transcription_form)],
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
    # Initialize variables outside try block to ensure they exist in finally block
    raw_transcript = ""
    cleaned_transcript = None
    transcription_logger: TranscriptionLogger | None = None

    try:
        # Extract and validate audio file
        audio_file = await _extract_audio_file_from_request(request, audio)
        _validate_audio_file(audio_file)

        # Extract form data (Pydantic handles string->bool conversion automatically)
        cleanup = form_data.cleanup
        extra_instructions = form_data.extra_instructions

        # Load all configurations
        (
            provider_cfg,
            wyoming_asr_cfg,
            openai_asr_cfg,
            gemini_asr_cfg,
            ollama_cfg,
            openai_llm_cfg,
            gemini_llm_cfg,
            defaults,
        ) = _load_transcription_configs()

        # Read uploaded file
        audio_data = await audio_file.read()
        LOGGER.info(
            "Received audio: filename=%s, size=%d bytes, content_type=%s",
            audio_file.filename,
            len(audio_data),
            audio_file.content_type,
        )

        # Convert audio to Wyoming format if using local ASR
        if provider_cfg.asr_provider == "wyoming":
            audio_data = _convert_audio_for_local_asr(audio_data, audio_file.filename)

        # Transcribe audio using the configured provider
        raw_transcript = await _transcribe_with_provider(
            audio_data,
            audio_file.filename or "audio.wav",
            provider_cfg,
            wyoming_asr_cfg,
            openai_asr_cfg,
            gemini_asr_cfg,
        )

        if not raw_transcript:
            return TranscriptionResponse(
                raw_transcript="",
                success=False,
                error="No transcript generated from audio",
            )

        if transcription_logger is None:
            try:
                transcription_logger = get_default_logger()
            except Exception as log_init_error:
                LOGGER.warning("Failed to initialize transcription logger: %s", log_init_error)

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
            transcription_logger.log_file if transcription_logger else None,
        )

        # If cleanup was requested but failed, indicate partial success
        if cleanup and cleaned_transcript is None:
            return TranscriptionResponse(
                raw_transcript=raw_transcript,
                cleaned_transcript=None,
                success=True,  # Transcription succeeded even if cleanup failed
                error="Transcription successful but cleanup failed. Check LLM configuration.",
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
        LOGGER.exception("Error during transcription")
        return TranscriptionResponse(raw_transcript="", success=False, error=str(e))
    finally:
        # Log the transcription automatically (even if it failed)
        # Only log if we have something to log
        if raw_transcript or cleaned_transcript:
            try:
                transcription_logger = transcription_logger or get_default_logger()
                transcription_logger.log_transcription(
                    raw=raw_transcript,
                    processed=cleaned_transcript,
                )
            except Exception as log_error:
                LOGGER.warning("Failed to log transcription: %s", log_error)
