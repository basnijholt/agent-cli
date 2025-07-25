"""FastAPI web service for Agent CLI transcription."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from agent_cli import config
from agent_cli.agents.transcribe import AGENT_INSTRUCTIONS, INSTRUCTION, SYSTEM_PROMPT
from agent_cli.core.config_utils import (
    create_asr_configs,
    create_llm_configs,
    create_provider_config_from_defaults,
    merge_extra_instructions,
)
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
    audio: Annotated[UploadFile, File()],
    cleanup: Annotated[bool, Form()] = True,
    extra_instructions: Annotated[str | None, Form()] = None,
) -> TranscriptionResponse:
    """Transcribe audio file and optionally clean up the text.

    Args:
        audio: Audio file (wav, mp3, m4a, etc.)
        cleanup: Whether to clean up transcription with LLM
        extra_instructions: Additional instructions for text cleanup

    Returns:
        TranscriptionResponse with raw and cleaned transcripts

    """
    if not audio.filename:
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
            temp_file.write(content)
            temp_file_path = Path(temp_file.name)

        try:
            # Load configuration from file
            loaded_config = config.load_config()
            defaults = loaded_config.get("defaults", {})

            # Create provider configuration from defaults
            provider_cfg = create_provider_config_from_defaults(defaults)

            # Create ASR configurations
            wyoming_asr_cfg, openai_asr_cfg = create_asr_configs(provider_cfg, defaults)

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
                # Create LLM configurations
                ollama_cfg, openai_cfg, gemini_cfg = create_llm_configs(provider_cfg, defaults)

                # Prepare instructions
                config_extra = loaded_config.get("transcribe", {}).get("extra_instructions", "")
                instructions = merge_extra_instructions(
                    AGENT_INSTRUCTIONS,
                    config_extra,
                    extra_instructions,
                )

                # Clean up transcript
                cleaned_transcript = await process_and_update_clipboard(
                    system_prompt=SYSTEM_PROMPT,
                    agent_instructions=instructions,
                    provider_cfg=provider_cfg,
                    ollama_cfg=ollama_cfg,
                    openai_cfg=openai_cfg,
                    gemini_cfg=gemini_cfg,
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
        logger.exception("Error during transcription")
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
