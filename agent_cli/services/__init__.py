"""Module for interacting with online services like OpenAI and Gemini."""

from __future__ import annotations

import io
import wave
from typing import TYPE_CHECKING

from agent_cli import constants

if TYPE_CHECKING:
    import logging

    from openai import AsyncOpenAI

    from agent_cli import config


_RIFF_HEADER = b"RIFF"
_LOG_TRUNCATE_LENGTH = 100


def _is_wav_file(data: bytes) -> bool:
    """Check if data is a WAV file by looking for RIFF header."""
    return len(data) >= len(_RIFF_HEADER) and data[: len(_RIFF_HEADER)] == _RIFF_HEADER


def pcm_to_wav(
    pcm_data: bytes,
    *,
    sample_rate: int = 16000,
    sample_width: int = 2,
    channels: int = 1,
) -> bytes:
    """Convert raw PCM audio data to WAV format.

    Args:
        pcm_data: Raw PCM audio bytes
        sample_rate: Sample rate in Hz (default: 16000)
        sample_width: Bytes per sample (default: 2 for 16-bit)
        channels: Number of audio channels (default: 1 for mono)

    Returns:
        WAV-formatted audio bytes

    """
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return wav_buffer.getvalue()


# Map file extensions to MIME types for Gemini
_GEMINI_MIME_TYPES: dict[str, str] = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".aiff": "audio/aiff",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",  # m4a is MP4 audio container
}

# Audio formats supported by Gemini (derived from MIME type mapping)
GEMINI_SUPPORTED_FORMATS: frozenset[str] = frozenset(_GEMINI_MIME_TYPES.keys())

# Audio formats supported by OpenAI Whisper API
OPENAI_SUPPORTED_FORMATS: frozenset[str] = frozenset(
    {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"},
)


_GEMINI_TRANSCRIPTION_PROMPT = (
    "Transcribe this audio accurately. Return only the transcription text, "
    "nothing else. Do not include any prefixes, labels, or explanations."
)


async def transcribe_audio_gemini(
    audio_data: bytes,
    gemini_asr_cfg: config.GeminiASR,
    logger: logging.Logger,
    *,
    file_suffix: str = ".wav",
    extra_instructions: str | None = None,
    **_kwargs: object,
) -> str:
    """Transcribe audio using Gemini's native audio understanding.

    Gemini can process audio natively and return transcriptions.
    Supports WAV, MP3, AIFF, AAC, OGG, and FLAC formats.

    Args:
        audio_data: Audio bytes (can be raw PCM or complete audio file)
        gemini_asr_cfg: Gemini ASR configuration
        logger: Logger instance
        file_suffix: File extension for MIME type detection (default: .wav)
        extra_instructions: Additional context/instructions to improve transcription

    """
    from google import genai  # noqa: PLC0415
    from google.genai import types  # noqa: PLC0415

    if not gemini_asr_cfg.gemini_api_key:
        msg = "Gemini API key is not set."
        raise ValueError(msg)

    logger.info("Transcribing audio with Gemini %s...", gemini_asr_cfg.asr_gemini_model)

    # Determine MIME type from file suffix
    mime_type = _GEMINI_MIME_TYPES.get(file_suffix.lower(), "audio/wav")

    logger.debug(
        "Received audio: size=%d bytes, file_suffix=%s, is_wav=%s",
        len(audio_data),
        file_suffix,
        _is_wav_file(audio_data),
    )

    # If raw PCM (no recognized format header), convert to WAV
    # Only do this if file_suffix is .wav but data doesn't have WAV header (indicating raw PCM)
    if not _is_wav_file(audio_data) and file_suffix.lower() == ".wav":
        logger.debug("Wrapping raw PCM data with WAV header (16kHz, 16-bit, mono)")
        audio_data = pcm_to_wav(
            audio_data,
            sample_rate=constants.AUDIO_RATE,
            sample_width=constants.AUDIO_FORMAT_WIDTH,
            channels=constants.AUDIO_CHANNELS,
        )

    logger.debug("Using MIME type: %s", mime_type)

    # Build the transcription prompt with optional context
    effective_prompt = gemini_asr_cfg.get_effective_prompt(extra_instructions)
    if effective_prompt:
        prompt = f"{_GEMINI_TRANSCRIPTION_PROMPT}\n\nContext: {effective_prompt}"
        logger.debug("Using Gemini ASR with context prompt")
    else:
        prompt = _GEMINI_TRANSCRIPTION_PROMPT

    client = genai.Client(api_key=gemini_asr_cfg.gemini_api_key)

    response = await client.aio.models.generate_content(
        model=gemini_asr_cfg.asr_gemini_model,
        contents=[
            prompt,
            types.Part.from_bytes(data=audio_data, mime_type=mime_type),
        ],
    )
    text = response.text.strip()

    if text:
        logger.info(
            "Transcription result: %s",
            text[:_LOG_TRUNCATE_LENGTH] + "..." if len(text) > _LOG_TRUNCATE_LENGTH else text,
        )
    else:
        logger.warning(
            "Empty transcription returned - audio may be silent, corrupted, or in wrong format",
        )

    return text


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
    *,
    file_suffix: str = ".wav",
    extra_instructions: str | None = None,
    **_kwargs: object,  # Accept extra kwargs for consistency with Wyoming
) -> str:
    """Transcribe audio using OpenAI's Whisper API or a compatible endpoint.

    OpenAI Whisper supports: mp3, mp4, mpeg, mpga, m4a, wav, and webm formats.

    When openai_base_url is set, uses the custom endpoint instead of the official OpenAI API.
    This allows using self-hosted Whisper models or other compatible services.

    Args:
        audio_data: Audio bytes (can be raw PCM or complete audio file)
        openai_asr_cfg: OpenAI ASR configuration
        logger: Logger instance
        file_suffix: File extension for filename (default: .wav)
        extra_instructions: Additional context/instructions to improve transcription

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

    logger.debug(
        "Received audio: size=%d bytes, file_suffix=%s, is_wav=%s",
        len(audio_data),
        file_suffix,
        _is_wav_file(audio_data),
    )

    # Convert raw PCM to WAV if needed (custom endpoints like faster-whisper require proper format)
    # Only do this if file_suffix is .wav but data doesn't have WAV header (indicating raw PCM)
    if not _is_wav_file(audio_data) and file_suffix.lower() == ".wav":
        logger.debug("Wrapping raw PCM data with WAV header (16kHz, 16-bit, mono)")
        audio_data = pcm_to_wav(
            audio_data,
            sample_rate=constants.AUDIO_RATE,
            sample_width=constants.AUDIO_FORMAT_WIDTH,
            channels=constants.AUDIO_CHANNELS,
        )

    audio_file = io.BytesIO(audio_data)
    # Use the correct file extension so OpenAI knows the format
    audio_file.name = f"audio{file_suffix}"

    logger.debug("Sending to OpenAI with filename: %s", audio_file.name)

    transcription_params: dict[str, object] = {
        "model": openai_asr_cfg.asr_openai_model,
        "file": audio_file,
    }

    # Get effective prompt combining config and extra_instructions
    effective_prompt = openai_asr_cfg.get_effective_prompt(extra_instructions)
    if effective_prompt:
        transcription_params["prompt"] = effective_prompt
        logger.debug("Using OpenAI ASR with prompt")

    response = await client.audio.transcriptions.create(**transcription_params)
    text = response.text

    if text:
        logger.info(
            "Transcription result: %s",
            text[:_LOG_TRUNCATE_LENGTH] + "..." if len(text) > _LOG_TRUNCATE_LENGTH else text,
        )
    else:
        logger.warning(
            "Empty transcription returned - audio may be silent, corrupted, or in wrong format",
        )

    return text


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
    return pcm_to_wav(pcm_data, sample_rate=24000)
