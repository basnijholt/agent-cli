"""Module for interacting with online services like OpenAI."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging

    from openai import AsyncOpenAI

    from agent_cli import config


def _get_openai_client(api_key: str | None, base_url: str | None = None) -> AsyncOpenAI:
    """Get an OpenAI client instance.

    For custom endpoints (base_url is set), API key is optional and a dummy value
    is used if not provided, since custom endpoints may not require authentication.
    """
    from openai import AsyncOpenAI  # noqa: PLC0415

    # Use dummy API key for custom endpoints if none provided
    effective_api_key = api_key or "dummy-api-key"
    return AsyncOpenAI(api_key=effective_api_key, base_url=base_url)


async def transcribe_audio_openai(
    audio_data: bytes,
    openai_asr_cfg: config.OpenAIASR,
    logger: logging.Logger,
    **_kwargs: object,  # Accept extra kwargs for consistency with Wyoming
) -> str:
    """Transcribe audio using OpenAI's Whisper API or a compatible endpoint.

    When openai_base_url is set, uses the custom endpoint instead of the official OpenAI API.
    This allows using self-hosted Whisper models or other compatible services.
    """
    if openai_asr_cfg.openai_base_url:
        logger.info(
            "Transcribing audio with custom OpenAI-compatible endpoint: %s",
            openai_asr_cfg.openai_base_url,
        )
    else:
        logger.info("Transcribing audio with OpenAI Whisper...")
        if not openai_asr_cfg.openai_api_key:
            msg = "OpenAI API key is not set."
            raise ValueError(msg)

    client = _get_openai_client(
        api_key=openai_asr_cfg.openai_api_key,
        base_url=openai_asr_cfg.openai_base_url,
    )
    audio_file = io.BytesIO(audio_data)
    audio_file.name = "audio.wav"

    transcription_params = {"model": openai_asr_cfg.asr_openai_model, "file": audio_file}
    if openai_asr_cfg.asr_openai_prompt:
        transcription_params["prompt"] = openai_asr_cfg.asr_openai_prompt

    response = await client.audio.transcriptions.create(**transcription_params)
    return response.text


async def synthesize_speech_openai(
    text: str,
    openai_tts_cfg: config.OpenAITTS,
    logger: logging.Logger,
) -> bytes:
    """Synthesize speech using OpenAI's TTS API or a compatible endpoint."""
    if openai_tts_cfg.tts_openai_base_url:
        logger.info(
            "Synthesizing speech with custom OpenAI-compatible endpoint: %s",
            openai_tts_cfg.tts_openai_base_url,
        )
    else:
        logger.info("Synthesizing speech with OpenAI TTS...")
        if not openai_tts_cfg.openai_api_key:
            msg = "OpenAI API key is not set."
            raise ValueError(msg)

    client = _get_openai_client(
        api_key=openai_tts_cfg.openai_api_key,
        base_url=openai_tts_cfg.tts_openai_base_url,
    )
    response = await client.audio.speech.create(
        model=openai_tts_cfg.tts_openai_model,
        voice=openai_tts_cfg.tts_openai_voice,
        input=text,
        response_format="wav",
    )
    return response.content
