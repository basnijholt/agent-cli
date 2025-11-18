"""Module for interacting with online services like OpenAI."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging

    from openai import AsyncOpenAI

    from agent_cli import config


def _get_openai_client(api_key: str) -> AsyncOpenAI:
    """Get an OpenAI client instance."""
    from openai import AsyncOpenAI  # noqa: PLC0415

    if not api_key:
        msg = "OpenAI API key is not set."
        raise ValueError(msg)
    return AsyncOpenAI(api_key=api_key)


async def transcribe_audio_openai(
    audio_data: bytes,
    openai_asr_cfg: config.OpenAIASR,
    logger: logging.Logger,
    **_kwargs: object,  # Accept extra kwargs for consistency with Wyoming
) -> str:
    """Transcribe audio using OpenAI's Whisper API."""
    logger.info("Transcribing audio with OpenAI Whisper...")
    if not openai_asr_cfg.openai_api_key:
        msg = "OpenAI API key is not set."
        raise ValueError(msg)
    client = _get_openai_client(api_key=openai_asr_cfg.openai_api_key)
    audio_file = io.BytesIO(audio_data)
    audio_file.name = "audio.wav"
    response = await client.audio.transcriptions.create(
        model=openai_asr_cfg.asr_openai_model,
        file=audio_file,
    )
    return response.text


async def transcribe_audio_custom(
    audio_data: bytes,
    custom_asr_cfg: config.CustomASR,
    logger: logging.Logger,
    **_kwargs: object,  # Accept extra kwargs for consistency with Wyoming
) -> str:
    """Transcribe audio using a custom Whisper-compatible API (e.g., NVIDIA Canary).

    This function communicates with a custom ASR endpoint that follows
    the OpenAI Whisper API format (/v1/audio/transcriptions).

    Args:
        audio_data: Audio bytes in WAV format (16kHz, mono recommended)
        custom_asr_cfg: Configuration with base_url, model, and prompt
        logger: Logger instance
        **_kwargs: Additional kwargs (for consistency with other providers)

    Returns:
        Transcribed text as a string

    """
    logger.info(
        "Transcribing audio with custom ASR endpoint: %s",
        custom_asr_cfg.asr_custom_base_url,
    )
    import httpx  # noqa: PLC0415

    # Prepare the multipart/form-data request
    files = {"file": ("audio.wav", audio_data, "audio/wav")}
    data = {}
    if custom_asr_cfg.asr_custom_model:
        data["model"] = custom_asr_cfg.asr_custom_model
    if custom_asr_cfg.asr_custom_prompt:
        data["prompt"] = custom_asr_cfg.asr_custom_prompt

    # Construct the full URL
    base_url = custom_asr_cfg.asr_custom_base_url.rstrip("/")
    url = f"{base_url}/v1/audio/transcriptions"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, files=files, data=data)
        response.raise_for_status()

        # Handle both JSON and plain text responses
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            result = response.json()
            return result.get("text", "")
        return response.text


async def synthesize_speech_openai(
    text: str,
    openai_tts_cfg: config.OpenAITTS,
    logger: logging.Logger,
) -> bytes:
    """Synthesize speech using OpenAI's TTS API."""
    logger.info("Synthesizing speech with OpenAI TTS...")
    if not openai_tts_cfg.openai_api_key:
        msg = "OpenAI API key is not set."
        raise ValueError(msg)
    client = _get_openai_client(api_key=openai_tts_cfg.openai_api_key)
    response = await client.audio.speech.create(
        model=openai_tts_cfg.tts_openai_model,
        voice=openai_tts_cfg.tts_openai_voice,
        input=text,
        response_format="wav",
    )
    return response.content
