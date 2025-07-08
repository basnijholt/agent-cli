"""Module for interacting with online services like OpenAI."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

if TYPE_CHECKING:
    import logging


async def transcribe_audio_openai(
    audio_data: bytes,
    api_key: str,
    logger: logging.Logger,
) -> str:
    """Transcribe audio using OpenAI's Whisper API."""
    logger.info("Transcribing audio with OpenAI Whisper...")
    client = AsyncOpenAI(api_key=api_key)
    audio_file = io.BytesIO(audio_data)
    audio_file.name = "audio.wav"
    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
    )
    return response.text


async def synthesize_speech_openai(
    text: str,
    api_key: str,
    logger: logging.Logger,
) -> bytes:
    """Synthesize speech using OpenAI's TTS API."""
    logger.info("Synthesizing speech with OpenAI TTS...")
    client = AsyncOpenAI(api_key=api_key)
    response = await client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
    )
    return response.content
