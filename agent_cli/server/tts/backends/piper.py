"""Piper TTS backend using piper-tts library."""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from typing import TYPE_CHECKING, Any

from agent_cli.server.tts.backends.base import (
    BackendConfig,
    InvalidTextError,
    SynthesisResult,
)

if TYPE_CHECKING:
    from piper import PiperVoice

logger = logging.getLogger(__name__)

# WAV header size in bytes (standard 44-byte header)
WAV_HEADER_SIZE = 44


def _load_model_sync(
    model_name: str,
    cache_dir: str | None,
) -> tuple[Any, int]:
    """Load Piper model synchronously (for use in process pool).

    Args:
        model_name: Model name or path.
        cache_dir: Optional cache directory for downloaded models.

    Returns:
        Tuple of (PiperVoice, sample_rate).

    """
    from piper import PiperVoice  # noqa: PLC0415
    from piper.download import ensure_voice_exists, find_voice, get_voices  # noqa: PLC0415

    # Get available voices
    voices = get_voices(cache_dir or None, update_voices=False)

    # Try to find the voice
    try:
        find_voice(model_name, voices)
    except ValueError:
        # Voice not in cache, try to download it
        voices = get_voices(cache_dir or None, update_voices=True)
        find_voice(model_name, voices)

    # Ensure model files exist
    model_path, config_path = ensure_voice_exists(
        model_name,
        cache_dir or None,
        cache_dir or None,
        voices,
    )

    # Load the voice
    voice = PiperVoice.load(model_path, config_path=config_path, use_cuda=False)

    return voice, voice.config.sample_rate


def _synthesize_sync(
    voice: PiperVoice,
    text: str,
    sample_rate: int,
    length_scale: float,
) -> tuple[bytes, float]:
    """Synthesize text to audio synchronously.

    Args:
        voice: Loaded PiperVoice instance.
        text: Text to synthesize.
        sample_rate: Sample rate from model config.
        length_scale: Length scale (inverse of speed).

    Returns:
        Tuple of (audio_bytes, duration_seconds).

    """
    # Create WAV buffer
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)

        # Synthesize with speed adjustment via length_scale
        for audio_bytes in voice.synthesize_stream_raw(
            text,
            length_scale=length_scale,
        ):
            wav_file.writeframes(audio_bytes)

    audio_data = buffer.getvalue()

    # Calculate duration: PCM data size / (sample_rate * channels * bytes_per_sample)
    data_size = len(audio_data) - WAV_HEADER_SIZE
    duration = data_size / (sample_rate * 1 * 2)

    return audio_data, duration


class PiperBackend:
    """Piper TTS backend using ONNX-based synthesis.

    This backend uses the piper-tts library for fast, CPU-friendly TTS.
    Models are downloaded from HuggingFace on first use.
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the Piper backend.

        Args:
            config: Backend configuration.

        """
        self._config = config
        self._voice: PiperVoice | None = None
        self._sample_rate: int = 22050  # Default, updated on load
        self._device: str | None = None

    @property
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        return self._voice is not None

    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on, or None if not loaded."""
        return self._device

    async def load(self) -> float:
        """Load the model into memory.

        Returns:
            Load duration in seconds.

        """
        if self._voice is not None:
            return 0.0

        start_time = time.time()

        # Load synchronously since Piper is fast and CPU-only
        loop = asyncio.get_event_loop()
        voice, sample_rate = await loop.run_in_executor(
            None,
            _load_model_sync,
            self._config.model_name,
            str(self._config.cache_dir) if self._config.cache_dir else None,
        )

        self._voice = voice
        self._sample_rate = sample_rate
        self._device = "cpu"  # Piper is CPU-only

        load_duration = time.time() - start_time
        logger.info(
            "Loaded Piper model %s in %.2fs (sample_rate=%d)",
            self._config.model_name,
            load_duration,
            self._sample_rate,
        )

        return load_duration

    async def unload(self) -> None:
        """Unload the model and free memory."""
        if self._voice is not None:
            logger.info("Unloading Piper model %s", self._config.model_name)
            self._voice = None
            self._device = None

    async def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,  # noqa: ARG002
        speed: float = 1.0,
    ) -> SynthesisResult:
        """Synthesize text to audio.

        Args:
            text: Text to synthesize.
            voice: Voice to use (not used for Piper - voice is the model).
            speed: Speech speed multiplier (0.25 to 4.0).

        Returns:
            SynthesisResult with audio data and metadata.

        Raises:
            InvalidTextError: If the text is empty or invalid.
            RuntimeError: If the model is not loaded.

        """
        if self._voice is None:
            msg = "Model not loaded"
            raise RuntimeError(msg)

        if not text or not text.strip():
            msg = "Text cannot be empty"
            raise InvalidTextError(msg)

        # Clamp speed to valid range
        speed = max(0.25, min(4.0, speed))

        # Convert speed to length_scale (inverse relationship)
        # length_scale < 1.0 = faster, > 1.0 = slower
        length_scale = 1.0 / speed

        # Run synthesis in executor to avoid blocking
        loop = asyncio.get_event_loop()
        audio_data, duration = await loop.run_in_executor(
            None,
            _synthesize_sync,
            self._voice,
            text,
            self._sample_rate,
            length_scale,
        )

        return SynthesisResult(
            audio=audio_data,
            sample_rate=self._sample_rate,
            sample_width=2,  # 16-bit
            channels=1,  # Mono
            duration=duration,
        )
