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
