"""FastAPI web service for Agent CLI transcription."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from agent_cli import config
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


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.post("/debug")
async def debug_request(request: Request) -> dict:
    """Debug endpoint to see raw request data."""
    body = await request.body()
    return {
        "headers": dict(request.headers),
        "content_type": request.headers.get("content-type"),
        "body_size": len(body),
        "body_preview": body[:500].decode("utf-8", errors="replace") if body else None,
    }


def _log_request_debug(
    request: Request,
    audio: UploadFile,
    cleanup: bool | str,
    extra_instructions: str | None,
) -> None:
    """Log debug information about the incoming request."""
    logger.info("=== Transcribe Request Debug ===")
    logger.info("Request headers: %s", dict(request.headers))
    logger.info("Audio filename: %s", audio.filename)
    logger.info("Audio content type: %s", audio.content_type)
    logger.info("Audio size: %s", audio.size if hasattr(audio, "size") else "unknown")
    logger.info("Cleanup parameter (raw): %r (type: %s)", cleanup, type(cleanup).__name__)
    logger.info("Extra instructions: %r", extra_instructions)


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
    # openai
    return await transcriber(
        audio_data=audio_data,
        openai_asr_cfg=openai_asr_cfg,
        logger=logger,
    )


@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    request: Request,
    audio: Annotated[UploadFile, File()],
    cleanup: Annotated[bool | str, Form()] = True,
    extra_instructions: Annotated[str | None, Form()] = None,
) -> TranscriptionResponse:
    """Transcribe audio file and optionally clean up the text.

    Args:
        request: FastAPI request object for debugging
        audio: Audio file (wav, mp3, m4a, etc.)
        cleanup: Whether to clean up transcription with LLM
        extra_instructions: Additional instructions for text cleanup

    Returns:
        TranscriptionResponse with raw and cleaned transcripts

    """
    # Debug logging for iOS Shortcuts
    _log_request_debug(request, audio, cleanup, extra_instructions)

    if not audio.filename:
        logger.error("No filename provided in request")
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate audio file type
    valid_extensions = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
    file_ext = Path(audio.filename).suffix.lower()
    if file_ext not in valid_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format: {file_ext}. Supported: {', '.join(valid_extensions)}",
        )

    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as temp_file:
            content = await audio.read()
            logger.info("Read %d bytes from uploaded audio", len(content))
            temp_file.write(content)
            temp_file_path = Path(temp_file.name)
            logger.info("Saved audio to temporary file: %s", temp_file_path)

        try:
            # Handle string boolean values from iOS Shortcuts
            if isinstance(cleanup, str):
                logger.info("Converting string cleanup value '%s' to boolean", cleanup)
                cleanup = cleanup.lower() == "true"
            logger.info("Final cleanup value: %s (type: %s)", cleanup, type(cleanup).__name__)

            # Load configuration from file and merge with transcribe-specific config
            loaded_config = config.load_config()
            wildcard_config = loaded_config.get("defaults", {})
            command_config = loaded_config.get("transcribe", {})
            defaults = {**wildcard_config, **command_config}

            # Create configurations just like transcribe.py does
            provider_cfg = config.ProviderSelection(
                asr_provider=defaults.get("asr_provider", "local"),
                llm_provider=defaults.get("llm_provider", "local"),
                tts_provider="local",  # Not used
            )
            wyoming_asr_cfg = config.WyomingASR(
                asr_wyoming_ip=defaults.get("asr_wyoming_ip", "localhost"),
                asr_wyoming_port=defaults.get("asr_wyoming_port", 10300),
            )
            openai_asr_cfg = config.OpenAIASR(
                asr_openai_model=defaults.get("asr_openai_model", "whisper-1"),
                openai_api_key=defaults.get("openai_api_key"),
            )
            ollama_cfg = config.Ollama(
                llm_ollama_model=defaults.get("llm_ollama_model", "qwen3:4b"),
                llm_ollama_host=defaults.get("llm_ollama_host", "http://localhost:11434"),
            )
            openai_llm_cfg = config.OpenAILLM(
                llm_openai_model=defaults.get("llm_openai_model", "gpt-4o-mini"),
                openai_api_key=defaults.get("openai_api_key"),
            )
            gemini_llm_cfg = config.GeminiLLM(
                llm_gemini_model=defaults.get("llm_gemini_model", "gemini-2.5-flash"),
                gemini_api_key=defaults.get("gemini_api_key"),
            )

            # Read audio file as bytes
            audio_data = temp_file_path.read_bytes()

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

            cleaned_transcript = None
            if cleanup:
                # Prepare instructions
                instructions = AGENT_INSTRUCTIONS
                config_extra = defaults.get("extra_instructions", "")
                if config_extra:
                    instructions += f"\n\n{config_extra}"
                if extra_instructions:
                    instructions += f"\n\n{extra_instructions}"

                # Clean up transcript
                cleaned_transcript = await process_and_update_clipboard(
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

            return TranscriptionResponse(
                raw_transcript=raw_transcript,
                cleaned_transcript=cleaned_transcript,
                success=True,
            )

        finally:
            # Clean up temporary file
            temp_file_path.unlink(missing_ok=True)

    except Exception as e:
        logger.exception(
            "Error during transcription - Exception type: %s, args: %s",
            type(e).__name__,
            e.args,
        )
        return TranscriptionResponse(
            raw_transcript="",
            success=False,
            error=str(e),
        )


def run_server(host: str = "0.0.0.0", port: int = 61337, reload: bool = False) -> None:  # noqa: S104
    """Run the FastAPI server."""
    uvicorn.run(
        "agent_cli.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
