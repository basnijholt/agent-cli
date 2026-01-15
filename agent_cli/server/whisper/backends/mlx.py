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
    release_memory,
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


class MLXWhisperBackend:
    """Whisper backend using mlx-whisper for Apple Silicon.

    Optimized for macOS with M1/M2/M3/M4 chips using Metal acceleration.
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the backend."""
        self._config = config
        self._resolved_model = _resolve_mlx_model_name(config.model_name)
        self._loaded = False
        self._model: object | None = None

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded.

        Note: mlx-whisper caches models internally. This tracks whether
        we've loaded the model at least once.
        """
        return self._loaded

    @property
    def device(self) -> str | None:
        """Get the device - always 'mps' (Metal) for MLX."""
        return "mps" if self._loaded else None

    async def load(self) -> float:
        """Load the model for MLX and warm the cache."""
        import time  # noqa: PLC0415

        logger.info(
            "Preparing mlx-whisper model %s (resolved: %s)",
            self._config.model_name,
            self._resolved_model,
        )

        start_time = time.time()

        from mlx_whisper.load_models import load_model  # noqa: PLC0415

        self._model = await asyncio.to_thread(load_model, self._resolved_model)

        self._loaded = True
        load_duration = time.time() - start_time

        logger.info(
            "Prepared mlx-whisper model %s in %.2fs",
            self._resolved_model,
            load_duration,
        )

        return load_duration

    async def unload(self) -> None:
        """Unload the model.

        Note: mlx-whisper caches models internally. We can trigger GC
        but full unload may require process restart for large models.
        """
        if not self._loaded:
            return

        logger.info("Unloading mlx-whisper model %s", self._resolved_model)

        self._model = None
        self._loaded = False
        release_memory()

        logger.info("Unloaded mlx-whisper model %s", self._resolved_model)

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

        # Run transcription in thread pool (mlx operations can block)
        result = await asyncio.to_thread(mlx_whisper.transcribe, audio_array, **kwargs)

        # Extract results - mlx_whisper returns a dict
        text = result.get("text", "").strip()
        detected_language = result.get("language", "en")

        # MLX doesn't provide language probability directly
        language_probability = 1.0 if language else 0.95

        # Calculate duration from segments or estimate from audio length
        segments = result.get("segments", [])
        # Estimate: 16kHz, 16-bit mono = 32000 bytes/second
        duration = segments[-1].get("end", 0.0) if segments else len(pcm_data) / 32000.0

        return TranscriptionResult(
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
