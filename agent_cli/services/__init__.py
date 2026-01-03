"""Module for interacting with online services like OpenAI and Gemini."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging

    from openai import AsyncOpenAI

    from agent_cli import config


_RIFF_HEADER = b"RIFF"


def _is_wav_file(data: bytes) -> bool:
    """Check if data is a WAV file by looking for RIFF header."""
    return len(data) >= len(_RIFF_HEADER) and data[: len(_RIFF_HEADER)] == _RIFF_HEADER


def _pcm_to_wav(pcm_data: bytes) -> bytes:
    """Convert raw PCM audio data to WAV format with headers."""
    import wave  # noqa: PLC0415

    from agent_cli import constants  # noqa: PLC0415

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(constants.AUDIO_CHANNELS)
        wav_file.setsampwidth(constants.AUDIO_FORMAT_WIDTH)  # 16-bit audio
        wav_file.setframerate(constants.AUDIO_RATE)
        wav_file.writeframes(pcm_data)
    return wav_buffer.getvalue()


async def transcribe_audio_gemini(
    audio_data: bytes,
    gemini_asr_cfg: config.GeminiASR,
    logger: logging.Logger,
    **_kwargs: object,
) -> str:
    """Transcribe audio using Gemini's native audio understanding.

    Gemini can process audio natively and return transcriptions.
    Supports WAV, MP3, AIFF, AAC, OGG, and FLAC formats.

    Accepts either raw PCM audio data or complete WAV files. Raw PCM
    is automatically converted to WAV format since Gemini requires it.
    """
    from google import genai  # noqa: PLC0415
    from google.genai import types  # noqa: PLC0415

    if not gemini_asr_cfg.gemini_api_key:
        msg = "Gemini API key is not set."
        raise ValueError(msg)

    logger.info("Transcribing audio with Gemini %s...", gemini_asr_cfg.asr_gemini_model)

    # Gemini requires complete WAV files with headers, not raw PCM
    # Auto-convert raw PCM to WAV if needed
    if not _is_wav_file(audio_data):
        logger.debug("Converting raw PCM to WAV format for Gemini")
        audio_data = _pcm_to_wav(audio_data)

    client = genai.Client(api_key=gemini_asr_cfg.gemini_api_key)

    response = await client.aio.models.generate_content(
        model=gemini_asr_cfg.asr_gemini_model,
        contents=[
            "Transcribe this audio accurately. Return only the transcription text, "
            "nothing else. Do not include any prefixes, labels, or explanations.",
            types.Part.from_bytes(data=audio_data, mime_type="audio/wav"),
        ],
    )
    return response.text.strip()


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


async def synthesize_speech_gemini(
    text: str,
    gemini_tts_cfg: config.GeminiTTS,
    logger: logging.Logger,
) -> bytes:
    """Synthesize speech using Gemini's native TTS.

    Returns WAV audio data (converted from Gemini's raw PCM output).
    """
    from google import genai  # noqa: PLC0415
    from google.genai import types  # noqa: PLC0415

    if not gemini_tts_cfg.gemini_api_key:
        msg = "Gemini API key is not set."
        raise ValueError(msg)

    logger.info(
        "Synthesizing speech with Gemini %s (voice: %s)...",
        gemini_tts_cfg.tts_gemini_model,
        gemini_tts_cfg.tts_gemini_voice,
    )

    client = genai.Client(api_key=gemini_tts_cfg.gemini_api_key)

    response = await client.aio.models.generate_content(
        model=gemini_tts_cfg.tts_gemini_model,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=gemini_tts_cfg.tts_gemini_voice,
                    ),
                ),
            ),
        ),
    )

    # Gemini returns raw PCM: 24kHz, 16-bit, mono
    pcm_data = response.candidates[0].content.parts[0].inline_data.data
    return _pcm_to_wav_24k(pcm_data)


def _pcm_to_wav_24k(pcm_data: bytes) -> bytes:
    """Convert raw PCM audio (24kHz, 16-bit, mono) to WAV format."""
    import wave  # noqa: PLC0415

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(24000)  # 24kHz
        wav_file.writeframes(pcm_data)
    return wav_buffer.getvalue()
