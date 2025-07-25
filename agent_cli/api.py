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
from agent_cli.services import transcribe_audio_openai
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
            # Get default configuration
            provider_cfg = config.ProviderSelection(
                asr_provider="openai",  # Default to OpenAI for web service
                llm_provider="openai",
                tts_provider="local",
            )

            # Configure ASR with default model
            openai_asr_cfg = config.OpenAIASR(
                asr_openai_model="whisper-1",
                openai_api_key=None,  # Will use env var
            )

            # Read audio file as bytes
            audio_data = temp_file_path.read_bytes()

            # Transcribe audio using OpenAI
            raw_transcript = await transcribe_audio_openai(
                audio_data=audio_data,
                openai_asr_cfg=openai_asr_cfg,
                logger=logger,
            )

            if not raw_transcript:
                return TranscriptionResponse(
                    raw_transcript="",
                    success=False,
                    error="No transcript generated from audio",
                )

            cleaned_transcript = None
            if cleanup:
                # Configure LLM for cleanup with default model
                openai_llm_cfg = config.OpenAILLM(
                    llm_openai_model="gpt-4o-mini",
                    openai_api_key=None,  # Will use env var
                )

                # Prepare instructions
                instructions = AGENT_INSTRUCTIONS
                if extra_instructions:
                    instructions += f"\n\n{extra_instructions}"

                # Clean up transcript
                cleaned_transcript = await process_and_update_clipboard(
                    system_prompt=SYSTEM_PROMPT,
                    agent_instructions=instructions,
                    provider_cfg=provider_cfg,
                    ollama_cfg=config.Ollama(
                        llm_ollama_model="llama2",
                        llm_ollama_host="http://localhost:11434",
                    ),  # Not used
                    openai_cfg=openai_llm_cfg,
                    gemini_cfg=config.GeminiLLM(
                        llm_gemini_model="gemini-pro",
                        gemini_api_key=None,
                    ),  # Not used
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


def run_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False) -> None:  # noqa: S104
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
