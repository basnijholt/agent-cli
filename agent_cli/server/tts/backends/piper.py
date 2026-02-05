"""Piper TTS backend using piper-tts library with subprocess isolation."""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path
from typing import Any, NoReturn

from agent_cli import constants
from agent_cli.core.process import set_process_title
from agent_cli.server.tts.backends.base import (
    BackendConfig,
    InvalidTextError,
    SynthesisResult,
    get_backend_cache_dir,
)

logger = logging.getLogger(__name__)


# --- Subprocess state (only used within subprocess worker) ---
# This state persists across function calls within the subprocess because:
# 1. Model loading is expensive and must be reused across synthesis calls
# 2. The subprocess is long-lived (ProcessPoolExecutor reuses workers)


@dataclass
class _SubprocessState:
    """Container for subprocess-local state. Not shared with main process."""

    voice: Any = None
    sample_rate: int = constants.PIPER_DEFAULT_SAMPLE_RATE


_state = _SubprocessState()


def _load_model_in_subprocess(
    model_name: str,
    cache_dir: str | None,
) -> int:
    """Load Piper model in subprocess. Returns sample rate.

    Args:
        model_name: Model name (e.g., 'en_US-lessac-medium') or path to .onnx file.
        cache_dir: Optional cache directory for downloaded models.

    Returns:
        Sample rate of loaded model.

    """
    from piper import PiperVoice  # noqa: PLC0415
    from piper.download_voices import download_voice  # noqa: PLC0415

    set_process_title("tts-piper")

    # Use default cache dir if not specified
    download_dir = Path(cache_dir) if cache_dir else get_backend_cache_dir("piper")
    download_dir.mkdir(parents=True, exist_ok=True)

    # Check if model_name is already a path to an existing file
    model_path = Path(model_name)
    if model_path.exists() and model_path.suffix == ".onnx":
        # Direct path to model file
        voice = PiperVoice.load(str(model_path), use_cuda=False)
        _state.voice = voice
        _state.sample_rate = voice.config.sample_rate
        return _state.sample_rate

    # Otherwise, treat as a voice name and download if needed
    voice_code = model_name.strip()
    expected_model_path = download_dir / f"{voice_code}.onnx"

    if not expected_model_path.exists():
        logger.info("Downloading Piper voice: %s", voice_code)
        download_voice(voice_code, download_dir)

    # Load the voice and store in subprocess state
    voice = PiperVoice.load(str(expected_model_path), use_cuda=False)
    _state.voice = voice
    _state.sample_rate = voice.config.sample_rate

    return _state.sample_rate


def _synthesize_in_subprocess(
    text: str,
    length_scale: float,
) -> tuple[bytes, float]:
    """Synthesize text to audio in subprocess. Uses model from _state.

    Args:
        text: Text to synthesize.
        length_scale: Length scale (inverse of speed).

    Returns:
        Tuple of (audio_bytes, duration_seconds).

    """
    from piper import SynthesisConfig  # noqa: PLC0415

    if _state.voice is None:
        msg = "Model not loaded in subprocess. Call _load_model_in_subprocess first."
        raise RuntimeError(msg)

    # Create synthesis config with speed adjustment
    syn_config = SynthesisConfig(length_scale=length_scale)

    # Create WAV buffer
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(_state.sample_rate)

        # Synthesize and write audio chunks
        for audio_chunk in _state.voice.synthesize(text, syn_config):
            wav_file.writeframes(audio_chunk.audio_int16_bytes)

    audio_data = buffer.getvalue()

    # Calculate duration: PCM data size / (sample_rate * channels * bytes_per_sample)
    data_size = len(audio_data) - constants.WAV_HEADER_SIZE
    duration = data_size / (_state.sample_rate * 1 * 2)

    return audio_data, duration


class PiperBackend:
    """Piper TTS backend with subprocess isolation.

    Uses subprocess isolation: when unloaded, the subprocess terminates
    and all memory is freed by the OS. This ensures clean memory management.
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the Piper backend."""
        self._config = config
        self._executor: ProcessPoolExecutor | None = None
        self._sample_rate: int = constants.PIPER_DEFAULT_SAMPLE_RATE  # Updated on load
        self._device: str | None = None

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._executor is not None

    @property
    def device(self) -> str | None:
        """Get the device the model is on."""
        return self._device

    async def load(self) -> float:
        """Start subprocess and load model."""
        if self._executor is not None:
            return 0.0

        start_time = time.time()

        # Subprocess isolation: spawn context for clean state
        ctx = get_context("spawn")
        self._executor = ProcessPoolExecutor(max_workers=1, mp_context=ctx)

        loop = asyncio.get_running_loop()
        self._sample_rate = await loop.run_in_executor(
            self._executor,
            _load_model_in_subprocess,
            self._config.model_name,
            str(self._config.cache_dir) if self._config.cache_dir else None,
        )

        self._device = "cpu"  # Piper is CPU-only

        load_duration = time.time() - start_time
        logger.info(
            "Loaded Piper model %s on %s in %.2fs",
            self._config.model_name,
            self._device,
            load_duration,
        )
        return load_duration

    async def unload(self) -> None:
        """Shutdown subprocess, releasing all memory."""
        if self._executor is None:
            return
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._executor = None
        self._device = None
        logger.info("Piper model %s unloaded (subprocess terminated)", self._config.model_name)

    async def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,  # noqa: ARG002
        speed: float = 1.0,
    ) -> SynthesisResult:
        """Synthesize text to audio."""
        if self._executor is None:
            msg = "Model not loaded. Call load() first."
            raise RuntimeError(msg)

        if not text or not text.strip():
            msg = "Text cannot be empty"
            raise InvalidTextError(msg)

        # Convert speed to length_scale (inverse relationship)
        length_scale = 1.0 / speed

        loop = asyncio.get_running_loop()
        audio_data, duration = await loop.run_in_executor(
            self._executor,
            _synthesize_in_subprocess,
            text,
            length_scale,
        )

        return SynthesisResult(
            audio=audio_data,
            sample_rate=self._sample_rate,
            sample_width=2,
            channels=1,
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
