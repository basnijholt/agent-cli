"""MLX Whisper backend for macOS Apple Silicon."""

from __future__ import annotations

import asyncio
import io
import logging
import wave
from typing import TYPE_CHECKING, Literal

from agent_cli import constants
from agent_cli.core.audio_format import convert_audio_to_wyoming_format
from agent_cli.server.whisper.backends.base import (
    BackendConfig,
    InvalidAudioError,
    TranscriptionResult,
)

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# MLX model name mapping: canonical name -> HuggingFace repo
_MLX_MODEL_MAP: dict[str, str] = {
    # Direct mappings for common names
    "tiny": "mlx-community/whisper-tiny",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "turbo": "mlx-community/whisper-large-v3-turbo",
    # Quantized variants
    "large-v3-turbo-q4": "mlx-community/whisper-large-v3-turbo-q4",
}


def _resolve_mlx_model_name(model_name: str) -> str:
    """Resolve a model name to an MLX HuggingFace repo.

    If the name is already an mlx-community repo, return as-is.
    Otherwise, try to map common names to MLX repos.
    """
    # Already an MLX repo
    if model_name.startswith("mlx-community/"):
        return model_name

    # Try direct mapping
    if model_name in _MLX_MODEL_MAP:
        return _MLX_MODEL_MAP[model_name]

    # Try without common prefixes (e.g., "whisper-large-v3-turbo" -> "large-v3-turbo")
    for prefix in ("whisper-", "openai/whisper-"):
        if model_name.startswith(prefix):
            stripped = model_name[len(prefix) :]
            if stripped in _MLX_MODEL_MAP:
                return _MLX_MODEL_MAP[stripped]

    # Return as-is and let mlx_whisper handle it
    return model_name


def ensure_model_downloaded(model_name: str) -> None:
    """Download model files if not already cached, without loading into memory.

    This allows showing download progress at startup without using GPU memory.
    """
    from pathlib import Path  # noqa: PLC0415

    from huggingface_hub import snapshot_download  # noqa: PLC0415

    resolved = _resolve_mlx_model_name(model_name)
    model_path = Path(resolved)
    if not model_path.exists():
        logger.info("Downloading model %s...", resolved)
        snapshot_download(repo_id=resolved)
        logger.info("Model %s downloaded", resolved)


def _pcm_to_float(audio_bytes: bytes) -> NDArray[np.float32]:
    """Convert 16-bit PCM audio bytes to float32 array normalized to [-1, 1]."""
    import numpy as np  # noqa: PLC0415

    return np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0


def _extract_pcm_from_wav(wav_bytes: bytes) -> tuple[bytes, int, int, int]:
    """Extract raw PCM data and WAV parameters from WAV bytes."""
    with io.BytesIO(wav_bytes) as buf, wave.open(buf, "rb") as wav_file:
        return (
            wav_file.readframes(wav_file.getnframes()),
            wav_file.getframerate(),
            wav_file.getnchannels(),
            wav_file.getsampwidth(),
        )


def _convert_audio_to_pcm(audio_bytes: bytes, source_filename: str | None) -> bytes:
    """Convert audio bytes to raw PCM using FFmpeg."""
    filename = source_filename or "audio"
    try:
        return convert_audio_to_wyoming_format(audio_bytes, filename)
    except RuntimeError as exc:
        logger.warning("FFmpeg conversion failed for MLX Whisper: %s", exc)
        msg = (
            "Unsupported audio format for MLX Whisper. "
            "Provide a 16kHz mono 16-bit WAV file or install ffmpeg to convert uploads."
        )
        raise InvalidAudioError(msg) from exc


def _clear_mlx_caches() -> None:
    """Clear MLX caches - must be called from the same thread that did MLX work."""
    import gc  # noqa: PLC0415

    import mlx.core as mx  # noqa: PLC0415
    from mlx_whisper.transcribe import ModelHolder  # noqa: PLC0415

    # Clear ModelHolder cache
    ModelHolder.model = None
    ModelHolder.model_path = None

    # Clear mlx_whisper lru_caches
    try:
        from mlx_whisper.audio import hanning, mel_filters  # noqa: PLC0415

        mel_filters.cache_clear()
        hanning.cache_clear()
    except ImportError:
        pass

    try:
        from mlx_whisper.tokenizer import get_encoding, get_tokenizer  # noqa: PLC0415

        get_encoding.cache_clear()
        get_tokenizer.cache_clear()
    except ImportError:
        pass

    # Clear MLX caches
    gc.collect()
    mx.clear_cache()


class MLXWhisperBackend:
    """Whisper backend using mlx-whisper for Apple Silicon.

    Optimized for macOS with M1/M2/M3/M4 chips using Metal acceleration.

    Uses a dedicated single-thread executor so that MLX cache clearing
    happens in the same thread that created the allocations.
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the backend."""
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

        self._config = config
        self._resolved_model = _resolve_mlx_model_name(config.model_name)
        self._loaded = False
        self._model: object | None = None
        # Dedicated executor so cache clearing happens in the same thread
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx-whisper")

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded.

        Note: mlx-whisper caches models internally. This tracks whether
        we've loaded the model at least once.
        """
        return self._loaded

    def ensure_downloaded(self) -> None:
        """Download model files if not already cached, without loading into memory."""
        ensure_model_downloaded(self._config.model_name)

    @property
    def device(self) -> str | None:
        """Get the device - always 'mps' (Metal) for MLX."""
        return "mps" if self._loaded else None

    async def load(self) -> float:
        """Load the model for MLX and warm the cache.

        Uses ModelHolder.get_model() to ensure the model is cached in the same
        location that mlx_whisper.transcribe() uses, avoiding double loading.

        Note: We intentionally don't use asyncio.to_thread() here because it
        creates a Future that holds a reference to the model, preventing memory
        from being freed on unload. Loading is a one-time operation so briefly
        blocking the event loop is acceptable.
        """
        import time  # noqa: PLC0415

        import mlx.core as mx  # noqa: PLC0415
        from mlx_whisper.transcribe import ModelHolder  # noqa: PLC0415

        logger.debug(
            "Preparing mlx-whisper model %s (resolved: %s)",
            self._config.model_name,
            self._resolved_model,
        )

        start_time = time.time()

        # Use ModelHolder.get_model() instead of load_model() directly.
        # This populates the same cache that mlx_whisper.transcribe() uses,
        # preventing the model from being loaded twice.
        # Note: Not using asyncio.to_thread() to avoid Future holding model reference.
        dtype = mx.float16
        self._model = ModelHolder.get_model(self._resolved_model, dtype)

        self._loaded = True
        load_duration = time.time() - start_time

        logger.info(
            "Model %s loaded in %.2fs",
            self._config.model_name,
            load_duration,
        )

        return load_duration

    async def unload(self) -> None:
        """Unload the model and clear caches."""
        if not self._loaded:
            return

        logger.debug("Unloading mlx-whisper model %s", self._resolved_model)

        self._model = None
        self._loaded = False

        # Clear caches IN THE SAME THREAD that did MLX work
        # This is critical because MLX may use thread-local allocations
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, _clear_mlx_caches)

        # Shutdown and recreate executor to release any thread-local memory
        self._executor.shutdown(wait=True)
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx-whisper")

        logger.info("Model %s unloaded", self._config.model_name)

    async def transcribe(
        self,
        audio: bytes,
        *,
        source_filename: str | None = None,
        language: str | None = None,
        task: Literal["transcribe", "translate"] = "transcribe",
        initial_prompt: str | None = None,
        temperature: float = 0.0,
        vad_filter: bool = True,  # noqa: ARG002 - not supported by mlx-whisper
        word_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio using mlx-whisper."""
        import mlx_whisper  # noqa: PLC0415

        if not self._loaded:
            msg = "Model not loaded. Call load() first."
            raise RuntimeError(msg)

        # Extract PCM from WAV and convert to float32
        try:
            pcm_data, sample_rate, channels, sample_width = _extract_pcm_from_wav(audio)
        except (wave.Error, EOFError) as exc:
            logger.debug("WAV parsing failed (%s); converting with FFmpeg", exc)
            pcm_data = _convert_audio_to_pcm(audio, source_filename)
        else:
            if (
                sample_rate != constants.AUDIO_RATE
                or channels != constants.AUDIO_CHANNELS
                or sample_width != constants.AUDIO_FORMAT_WIDTH
            ):
                logger.debug(
                    "WAV format mismatch (rate=%s, channels=%s, width=%s); converting with FFmpeg",
                    sample_rate,
                    channels,
                    sample_width,
                )
                if source_filename and source_filename.lower().endswith(".wav"):
                    conversion_name = source_filename
                else:
                    conversion_name = "audio.wav"
                pcm_data = _convert_audio_to_pcm(audio, conversion_name)
        audio_array = _pcm_to_float(pcm_data)

        # Build kwargs for mlx_whisper.transcribe
        kwargs: dict[str, object] = {
            "path_or_hf_repo": self._resolved_model,
            "temperature": temperature,
            "word_timestamps": word_timestamps,
        }
        if language:
            kwargs["language"] = language
        if task == "translate":
            kwargs["task"] = "translate"
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        # Run transcription in dedicated executor (same thread for cache management)
        from functools import partial  # noqa: PLC0415

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            self._executor,
            partial(mlx_whisper.transcribe, audio_array, **kwargs),
        )

        # Extract results immediately and clear the result dict to help GC
        text = result.get("text", "").strip()
        detected_language = result.get("language", "en")

        # MLX doesn't provide language probability directly
        language_probability = 1.0 if language else 0.95

        # Calculate duration from segments or estimate from audio length
        segments = result.get("segments", [])
        # Estimate: 16kHz, 16-bit mono = 32000 bytes/second
        duration = segments[-1].get("end", 0.0) if segments else len(pcm_data) / 32000.0

        transcription_result = TranscriptionResult(
            text=text,
            language=detected_language,
            language_probability=language_probability,
            duration=duration,
            segments=[
                {
                    "id": i,
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                    "text": seg.get("text", ""),
                    "tokens": seg.get("tokens", []),
                    "avg_logprob": seg.get("avg_logprob", 0.0),
                    "no_speech_prob": seg.get("no_speech_prob", 0.0),
                }
                for i, seg in enumerate(segments)
            ],
        )

        # Clean up local references (actual cache clearing happens on unload in executor)
        del result, segments, audio_array, pcm_data

        return transcription_result
