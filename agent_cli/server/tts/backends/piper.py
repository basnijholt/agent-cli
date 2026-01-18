"""Piper TTS backend using piper-tts library."""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

from agent_cli import constants
from agent_cli.server.tts.backends.base import (
    BackendConfig,
    InvalidTextError,
    SynthesisResult,
    get_backend_cache_dir,
)

if TYPE_CHECKING:
    from piper import PiperVoice

logger = logging.getLogger(__name__)


def _load_model_sync(
    model_name: str,
    cache_dir: str | None,
) -> tuple[Any, int]:
    """Load Piper model synchronously (for use in process pool).

    Args:
        model_name: Model name (e.g., 'en_US-lessac-medium') or path to .onnx file.
        cache_dir: Optional cache directory for downloaded models.

    Returns:
        Tuple of (PiperVoice, sample_rate).

    """
    from piper import PiperVoice  # noqa: PLC0415
    from piper.download_voices import download_voice  # noqa: PLC0415

    # Use default cache dir if not specified
    download_dir = Path(cache_dir) if cache_dir else get_backend_cache_dir("piper")
    download_dir.mkdir(parents=True, exist_ok=True)

    # Check if model_name is already a path to an existing file
    model_path = Path(model_name)
    if model_path.exists() and model_path.suffix == ".onnx":
        # Direct path to model file
        voice = PiperVoice.load(str(model_path), use_cuda=False)
        return voice, voice.config.sample_rate

    # Otherwise, treat as a voice name and download if needed
    voice_code = model_name.strip()
    expected_model_path = download_dir / f"{voice_code}.onnx"

    if not expected_model_path.exists():
        logger.info("Downloading Piper voice: %s", voice_code)
        download_voice(voice_code, download_dir)

    # Load the voice
    voice = PiperVoice.load(str(expected_model_path), use_cuda=False)

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
    from piper import SynthesisConfig  # noqa: PLC0415

    # Create synthesis config with speed adjustment
    syn_config = SynthesisConfig(length_scale=length_scale)

    # Create WAV buffer
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)

        # Synthesize and write audio chunks
        for audio_chunk in voice.synthesize(text, syn_config):
            wav_file.writeframes(audio_chunk.audio_int16_bytes)

    audio_data = buffer.getvalue()

    # Calculate duration: PCM data size / (sample_rate * channels * bytes_per_sample)
    data_size = len(audio_data) - constants.WAV_HEADER_SIZE
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
        self._sample_rate: int = constants.PIPER_DEFAULT_SAMPLE_RATE  # Updated on load
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
        loop = asyncio.get_running_loop()
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

        # Convert speed to length_scale (inverse relationship)
        # Speed is already validated/clamped by the API layer
        # length_scale < 1.0 = faster, > 1.0 = slower
        length_scale = 1.0 / speed

        # Run synthesis in executor to avoid blocking.
        # Thread-safe: ONNX Runtime InferenceSession.run() is thread-safe since v1.10+,
        # so concurrent requests can share the same PiperVoice instance safely.
        loop = asyncio.get_running_loop()
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

    @property
    def supports_streaming(self) -> bool:
        """Piper backend does not support streaming synthesis."""
        return False

    def synthesize_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> NoReturn:
        """Streaming is not supported by Piper backend."""
        msg = "Streaming synthesis is not supported by Piper backend"
        raise NotImplementedError(msg)
