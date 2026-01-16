"""MLX Whisper backend for macOS Apple Silicon."""

from __future__ import annotations

import asyncio
import logging
import wave
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from typing import TYPE_CHECKING, Any, Literal

from agent_cli import constants
from agent_cli.core.audio_format import (
    convert_audio_to_wyoming_format,
    extract_pcm_from_wav,
)
from agent_cli.core.process import set_process_title
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
    "tiny": "mlx-community/whisper-tiny",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3-turbo-q4": "mlx-community/whisper-large-v3-turbo-q4",
}


def _resolve_mlx_model_name(model_name: str) -> str:
    """Resolve a model name to an MLX HuggingFace repo."""
    if model_name.startswith("mlx-community/"):
        return model_name
    if model_name in _MLX_MODEL_MAP:
        return _MLX_MODEL_MAP[model_name]
    for prefix in ("whisper-", "openai/whisper-"):
        if model_name.startswith(prefix):
            stripped = model_name[len(prefix) :]
            if stripped in _MLX_MODEL_MAP:
                return _MLX_MODEL_MAP[stripped]
    return model_name


def _pcm_to_float(audio_bytes: bytes) -> NDArray[np.float32]:
    """Convert 16-bit PCM audio bytes to float32 array normalized to [-1, 1]."""
    import numpy as np  # noqa: PLC0415

    return np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0


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


def _prepare_audio_pcm(audio: bytes, source_filename: str | None) -> bytes:
    """Extract PCM from WAV or convert with FFmpeg if needed."""
    try:
        wav = extract_pcm_from_wav(audio)
    except (wave.Error, EOFError) as exc:
        logger.debug("WAV parsing failed (%s); converting with FFmpeg", exc)
        return _convert_audio_to_pcm(audio, source_filename)

    needs_conversion = (
        wav.sample_rate != constants.AUDIO_RATE
        or wav.num_channels != constants.AUDIO_CHANNELS
        or wav.sample_width != constants.AUDIO_FORMAT_WIDTH
    )
    if needs_conversion:
        logger.debug(
            "WAV format mismatch (rate=%s, channels=%s, width=%s); converting",
            wav.sample_rate,
            wav.num_channels,
            wav.sample_width,
        )
        name = (
            source_filename
            if source_filename and source_filename.lower().endswith(".wav")
            else "audio.wav"
        )
        return _convert_audio_to_pcm(audio, name)
    return wav.pcm_data


# --- Subprocess worker functions (run in isolated process) ---


def _load_model_in_subprocess(model_name: str) -> None:
    """Load model in subprocess. Called once when executor starts."""
    import mlx.core as mx  # noqa: PLC0415
    from mlx_whisper.transcribe import ModelHolder  # noqa: PLC0415

    set_process_title("whisper-mlx")
    ModelHolder.get_model(model_name, mx.float16)


def _transcribe_in_subprocess(
    model_name: str,
    audio_bytes: bytes,
    audio_shape: tuple[int, ...],
    audio_dtype: str,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Run transcription in subprocess. Model stays loaded between calls."""
    import mlx_whisper  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    audio_array = np.frombuffer(audio_bytes, dtype=audio_dtype).reshape(audio_shape)
    result = mlx_whisper.transcribe(audio_array, path_or_hf_repo=model_name, **kwargs)

    return {
        "text": result.get("text", ""),
        "language": result.get("language", "en"),
        "segments": result.get("segments", []),
    }


class MLXWhisperBackend:
    """Whisper backend using mlx-whisper for Apple Silicon.

    Uses subprocess isolation: when unloaded, the subprocess terminates
    and the OS reclaims ALL memory (Python's pymalloc doesn't return
    freed memory to OS otherwise).
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the backend."""
        self._config = config
        self._resolved_model = _resolve_mlx_model_name(config.model_name)
        self._executor: ProcessPoolExecutor | None = None

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._executor is not None

    @property
    def device(self) -> str | None:
        """Get the device - always 'mps' (Metal) for MLX."""
        return "mps" if self._executor is not None else None

    async def load(self) -> float:
        """Start subprocess and load model."""
        import time  # noqa: PLC0415

        logger.debug(
            "Starting MLX subprocess for model %s (resolved: %s)",
            self._config.model_name,
            self._resolved_model,
        )

        start_time = time.time()

        # Subprocess isolation: spawn context for clean state
        ctx = get_context("spawn")
        self._executor = ProcessPoolExecutor(max_workers=1, mp_context=ctx)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            self._executor,
            _load_model_in_subprocess,
            self._resolved_model,
        )

        load_duration = time.time() - start_time
        logger.info(
            "Model %s loaded in subprocess in %.2fs",
            self._config.model_name,
            load_duration,
        )
        return load_duration

    async def unload(self) -> None:
        """Shutdown subprocess, releasing ALL memory."""
        if self._executor is None:
            return
        logger.debug("Shutting down MLX subprocess for model %s", self._resolved_model)
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._executor = None
        logger.info("Model %s unloaded (subprocess terminated)", self._config.model_name)

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
        """Transcribe audio using mlx-whisper in subprocess."""
        if self._executor is None:
            msg = "Model not loaded. Call load() first."
            raise RuntimeError(msg)

        pcm_data = _prepare_audio_pcm(audio, source_filename)
        audio_array = _pcm_to_float(pcm_data)

        kwargs: dict[str, Any] = {
            "temperature": temperature,
            "word_timestamps": word_timestamps,
        }
        if language:
            kwargs["language"] = language
        if task == "translate":
            kwargs["task"] = "translate"
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            self._executor,
            _transcribe_in_subprocess,
            self._resolved_model,
            audio_array.tobytes(),
            audio_array.shape,
            str(audio_array.dtype),
            kwargs,
        )

        text = result.get("text", "").strip()
        detected_language = result.get("language", "en")
        language_probability = 1.0 if language else 0.95
        segments = result.get("segments", [])
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
