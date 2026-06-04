"""NeMo backend for NVIDIA ASR models (for example, Parakeet)."""

from __future__ import annotations

import asyncio
import inspect
import io
import logging
import os
import sys
import tempfile
import time
import wave
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Literal

from agent_cli.core.audio_format import convert_audio_to_wav_format
from agent_cli.core.process import set_process_title
from agent_cli.server.whisper.backends.base import (
    BackendConfig,
    InvalidAudioError,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)

# Model aliases for convenience in CLI usage. Keep these to public NVIDIA
# Parakeet model IDs so bare names resolve predictably.
_PARAKEET_ALIASES = (
    "parakeet-tdt-0.6b-v2",
    "parakeet-tdt-0.6b-v3",
    "parakeet-unified-en-0.6b",
    "parakeet-tdt-1.1b",
    "parakeet-ctc-0.6b",
    "parakeet-ctc-1.1b",
    "parakeet-rnnt-0.6b",
    "parakeet-rnnt-1.1b",
    "parakeet-tdt_ctc-110m",
)
_MODEL_MAP: dict[str, str] = {alias: f"nvidia/{alias}" for alias in _PARAKEET_ALIASES}


def is_parakeet_model_name(model_name: str) -> bool:
    """Return True when a model name targets NVIDIA Parakeet."""
    normalized = model_name.strip().lower()
    return normalized in _MODEL_MAP or normalized.startswith("nvidia/parakeet-")


def _resolve_model_name(model_name: str) -> str:
    """Resolve a model name to a NeMo Hub identifier."""
    normalized = model_name.strip()
    lowered = normalized.lower()

    if "/" in normalized:
        if is_parakeet_model_name(normalized):
            return lowered
        return normalized
    return _MODEL_MAP.get(lowered, normalized)


def download_model(model_name: str) -> str:
    """Download a NeMo ASR model and return the resolved model identifier."""
    import nemo.collections.asr as nemo_asr  # noqa: PLC0415

    resolved_model = _resolve_model_name(model_name)
    _ = nemo_asr.models.ASRModel.from_pretrained(model_name=resolved_model)
    return resolved_model


# --- Subprocess state (only used within subprocess worker) ---
# This state persists across function calls within the subprocess because:
# 1. Model loading is expensive and must be reused across transcription calls
# 2. NeMo models cannot be pickled/passed through IPC queues
# 3. The subprocess is long-lived (ProcessPoolExecutor reuses workers)


@dataclass
class _SubprocessState:
    """Container for subprocess-local state. Not shared with main process."""

    model: Any = None
    device: str | None = None


_state = _SubprocessState()


def _resolve_device(device: str) -> str:
    """Resolve the runtime device for NeMo inference."""
    if device in {"auto", "mps"} and sys.platform == "darwin":
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    import torch  # noqa: PLC0415

    if device == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if _mps_available(torch):
            return "mps"
        return "cpu"

    if device.startswith("cuda") and not torch.cuda.is_available():
        msg = f"CUDA device requested ({device}) but CUDA is not available"
        raise RuntimeError(msg)

    if device == "mps" and not _mps_available(torch):
        msg = "MPS device requested (mps) but MPS is not available"
        raise RuntimeError(msg)

    return device


def _mps_available(torch: Any) -> bool:
    """Return True when PyTorch exposes an available MPS backend."""
    mps = getattr(getattr(torch, "backends", None), "mps", None)
    return bool(mps is not None and mps.is_available())


def _extract_text(hypothesis: Any) -> str:
    """Extract a transcript string from a NeMo hypothesis-like object."""
    if isinstance(hypothesis, str):
        return hypothesis.strip()

    if isinstance(hypothesis, dict):
        return str(hypothesis.get("text", "")).strip()

    return str(getattr(hypothesis, "text", "")).strip()


def _extract_segments(hypothesis: Any, *, word_timestamps: bool) -> list[dict[str, Any]]:
    """Extract segment metadata from NeMo timestamp output.

    Parakeet hypotheses expose timestamp["segment"] and timestamp["word"] lists.
    """
    timestamp = getattr(hypothesis, "timestamp", None)
    if timestamp is None and isinstance(hypothesis, dict):
        timestamp = hypothesis.get("timestamp")

    if not isinstance(timestamp, dict):
        return []

    list_key, text_key = ("word", "word") if word_timestamps else ("segment", "segment")
    entries = timestamp.get(list_key)
    if not isinstance(entries, list):
        return []

    segments: list[dict[str, Any]] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        start = float(entry.get("start", 0.0) or 0.0)
        end = float(entry.get("end", start) or start)
        text = str(entry.get(text_key, "")).strip()
        segments.append(
            {
                "id": idx,
                "start": start,
                "end": end,
                "text": text,
                "tokens": [],
                "avg_logprob": 0.0,
                "no_speech_prob": 0.0,
            },
        )

    return segments


def _audio_duration_seconds(wav_path: str) -> float:
    """Read WAV duration in seconds."""
    try:
        with wave.open(wav_path, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            if sample_rate <= 0:
                return 0.0
            return wav_file.getnframes() / sample_rate
    except (wave.Error, EOFError):
        return 0.0


def _prepare_audio_for_nemo(audio_bytes: bytes, source_filename: str | None) -> bytes:
    """Return a WAV container suitable for NeMo file-path transcription."""
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb"):
            return audio_bytes
    except (wave.Error, EOFError):
        pass

    filename = source_filename or "audio"
    try:
        return convert_audio_to_wav_format(audio_bytes, filename)
    except RuntimeError as exc:
        logger.warning("FFmpeg conversion failed for NeMo Whisper: %s", exc)
        msg = (
            "Unsupported audio format for NeMo Whisper. "
            "Provide a WAV file or install ffmpeg to convert uploads."
        )
        raise InvalidAudioError(msg) from exc


def _build_transcribe_kwargs(
    transcribe_func: Any,
    *,
    language: str | None,
    word_timestamps: bool,  # noqa: ARG001 - extraction granularity; NeMo always computes timestamps.
) -> dict[str, Any]:
    """Build NeMo transcribe kwargs supported by the loaded model signature."""
    transcribe_kwargs: dict[str, Any] = {"timestamps": True}
    if not language:
        return transcribe_kwargs

    try:
        parameters = inspect.signature(transcribe_func).parameters
    except (TypeError, ValueError):
        return transcribe_kwargs

    has_var_keyword = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )

    if "target_lang" in parameters or has_var_keyword:
        transcribe_kwargs["target_lang"] = language

    return transcribe_kwargs


def _set_config_value(config: Any, key: str, value: Any) -> None:
    """Set a NeMo config value, including OmegaConf configs in struct mode."""
    try:
        setattr(config, key, value)
        return
    except (AttributeError, TypeError):
        if isinstance(config, dict):
            config[key] = value
            return
        raise
    except Exception:
        from omegaconf import open_dict  # noqa: PLC0415

        with open_dict(config):
            setattr(config, key, value)


def _ensure_validation_ds_config(model: Any) -> None:
    """NeMo RNNT transcribe expects cfg.validation_ds to be a mapping."""
    config = getattr(model, "cfg", None)
    if config is None:
        return

    try:
        validation_ds = (
            config.get("validation_ds") if hasattr(config, "get") else config.validation_ds
        )
    except (AttributeError, KeyError):
        return

    if validation_ds is None:
        # TODO(NVIDIA-NeMo/NeMo#15752): Drop after NeMo release.  # noqa: FIX002
        _set_config_value(config, "validation_ds", {})


def _load_model_in_subprocess(model_name: str, device: str) -> str:
    """Load model in subprocess. Returns actual device string."""
    import nemo.collections.asr as nemo_asr  # noqa: PLC0415

    set_process_title("whisper-nemo")

    resolved_device = _resolve_device(device)
    model = nemo_asr.models.ASRModel.from_pretrained(model_name=model_name)
    _ensure_validation_ds_config(model)
    if hasattr(model, "to"):
        model = model.to(resolved_device)
    if hasattr(model, "eval"):
        model.eval()

    _state.model = model
    _state.device = resolved_device
    return resolved_device


def _transcribe_in_subprocess(
    audio_bytes: bytes,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Run transcription in subprocess. Reuses model from _state."""
    if _state.model is None:
        msg = "Model not loaded in subprocess. Call _load_model_in_subprocess first."
        raise RuntimeError(msg)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        transcribe_kwargs = _build_transcribe_kwargs(
            _state.model.transcribe,
            language=kwargs["language"],
            word_timestamps=kwargs["word_timestamps"],
        )
        outputs = _state.model.transcribe([tmp_path], **transcribe_kwargs)

        hypothesis: Any | None = None
        if isinstance(outputs, list) and outputs:
            hypothesis = outputs[0]
        elif outputs:
            hypothesis = outputs

        text = _extract_text(hypothesis) if hypothesis is not None else ""
        segments = (
            _extract_segments(hypothesis, word_timestamps=kwargs["word_timestamps"])
            if hypothesis is not None
            else []
        )
        duration = _audio_duration_seconds(tmp_path)

    finally:
        Path(tmp_path).unlink(missing_ok=True)

    language = kwargs["language"] or "en"
    language_probability = 1.0 if kwargs["language"] else 0.95
    return {
        "text": text,
        "language": language,
        "language_probability": language_probability,
        "duration": duration,
        "segments": segments,
    }


class NemoWhisperBackend:
    """ASR backend using NVIDIA NeMo models.

    One worker process is intentional: one loaded NeMo model owns process memory
    or VRAM, so requests for a loaded model are serialized.
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the backend."""
        self._config = config
        self._resolved_model = _resolve_model_name(config.model_name)
        self._executor: ProcessPoolExecutor | None = None
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
        logger.debug(
            "Starting NeMo subprocess for model %s (resolved: %s, device=%s)",
            self._config.model_name,
            self._resolved_model,
            self._config.device,
        )

        start_time = time.time()

        ctx = get_context("spawn")
        self._executor = ProcessPoolExecutor(max_workers=1, mp_context=ctx)

        loop = asyncio.get_running_loop()
        try:
            self._device = await loop.run_in_executor(
                self._executor,
                _load_model_in_subprocess,
                self._resolved_model,
                self._config.device,
            )
        except Exception:
            executor = self._executor
            self._executor = None
            self._device = None
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)
            raise

        load_duration = time.time() - start_time
        logger.info(
            "Model %s loaded on %s in %.2fs",
            self._config.model_name,
            self._device,
            load_duration,
        )
        return load_duration

    async def unload(self) -> None:
        """Shutdown subprocess, releasing all memory."""
        if self._executor is None:
            return
        executor = self._executor
        self._executor = None
        self._device = None
        logger.debug(
            "Shutting down NeMo subprocess for model %s",
            self._config.model_name,
        )
        await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)
        logger.info("Model %s unloaded (subprocess shut down)", self._config.model_name)

    async def transcribe(
        self,
        audio: bytes,
        *,
        source_filename: str | None = None,
        language: str | None = None,
        task: Literal["transcribe", "translate"] = "transcribe",  # noqa: ARG002
        initial_prompt: str | None = None,  # noqa: ARG002
        temperature: float = 0.0,  # noqa: ARG002
        vad_filter: bool = True,  # noqa: ARG002
        word_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio using NeMo in subprocess."""
        if self._executor is None:
            msg = "Model not loaded. Call load() first."
            raise RuntimeError(msg)

        audio = await asyncio.to_thread(_prepare_audio_for_nemo, audio, source_filename)

        kwargs: dict[str, Any] = {
            "language": language,
            "word_timestamps": word_timestamps,
        }

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                self._executor,
                _transcribe_in_subprocess,
                audio,
                kwargs,
            )
        except BrokenProcessPool:
            logger.warning(
                "NeMo subprocess for model %s died; reloading and retrying once",
                self._config.model_name,
            )
            await self.unload()
            await self.load()
            if self._executor is None:
                msg = "Model reload failed after NeMo subprocess died."
                raise RuntimeError(msg) from None
            result = await loop.run_in_executor(
                self._executor,
                _transcribe_in_subprocess,
                audio,
                kwargs,
            )

        return TranscriptionResult(
            text=result["text"],
            language=result["language"],
            language_probability=result["language_probability"],
            duration=result["duration"],
            segments=result["segments"],
        )
