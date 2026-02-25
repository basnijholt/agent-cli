"""NeMo backend for NVIDIA ASR models (for example, Parakeet)."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import wave
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Literal

from agent_cli.core.process import set_process_title
from agent_cli.server.whisper.backends.base import (
    BackendConfig,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)

# Model aliases for convenience in CLI usage.
_MODEL_MAP: dict[str, str] = {
    "parakeet-tdt-0.6b-v2": "nvidia/parakeet-tdt-0.6b-v2",
}


def _resolve_model_name(model_name: str) -> str:
    """Resolve a model name to a NeMo Hub identifier."""
    if "/" in model_name:
        return model_name
    return _MODEL_MAP.get(model_name, model_name)


def download_model(model_name: str) -> str:
    """Download a NeMo ASR model and return the resolved model identifier."""
    import nemo.collections.asr as nemo_asr  # noqa: PLC0415

    resolved_model = _resolve_model_name(model_name)
    _ = nemo_asr.models.ASRModel.from_pretrained(model_name=resolved_model)
    return resolved_model


@dataclass
class _SubprocessState:
    """Container for subprocess-local state. Not shared with main process."""

    model: Any = None
    device: str | None = None


_state = _SubprocessState()


def _resolve_device(device: str) -> str:
    """Resolve the runtime device for NeMo inference."""
    import torch  # noqa: PLC0415

    if device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"

    if device.startswith("cuda") and not torch.cuda.is_available():
        msg = f"CUDA device requested ({device}) but CUDA is not available"
        raise RuntimeError(msg)

    return device


def _extract_text(hypothesis: Any) -> str:
    """Extract a transcript string from a NeMo hypothesis-like object."""
    if isinstance(hypothesis, str):
        return hypothesis.strip()

    if isinstance(hypothesis, dict):
        return str(hypothesis.get("text", "")).strip()

    return str(getattr(hypothesis, "text", "")).strip()


def _extract_segments(hypothesis: Any, *, word_timestamps: bool) -> list[dict[str, Any]]:
    """Extract segment metadata from NeMo timestamp output when available."""
    timestamp = getattr(hypothesis, "timestamp", None)
    if timestamp is None and isinstance(hypothesis, dict):
        timestamp = hypothesis.get("timestamp")

    if not isinstance(timestamp, dict):
        return []

    key_order = ["segment", "word"] if word_timestamps else ["segment"]
    for key in key_order:
        entries = timestamp.get(key)
        if not isinstance(entries, list):
            continue

        segments: list[dict[str, Any]] = []
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            start = float(entry.get("start", 0.0) or 0.0)
            end = float(entry.get("end", start) or start)
            text = str(
                entry.get("segment")
                or entry.get("word")
                or entry.get("char")
                or entry.get("text")
                or "",
            ).strip()
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
        if segments:
            return segments

    return []


def _audio_duration_seconds(wav_path: str) -> float:
    """Read WAV duration in seconds."""
    with wave.open(wav_path, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        if sample_rate <= 0:
            return 0.0
        return wav_file.getnframes() / sample_rate


def _load_model_in_subprocess(model_name: str, device: str) -> str:
    """Load model in subprocess. Returns actual device string."""
    import nemo.collections.asr as nemo_asr  # noqa: PLC0415

    set_process_title("whisper-nemo")

    resolved_device = _resolve_device(device)
    model = nemo_asr.models.ASRModel.from_pretrained(model_name=model_name)
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
        outputs = _state.model.transcribe(
            [tmp_path],
            timestamps=kwargs["word_timestamps"],
        )

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
    """ASR backend using NVIDIA NeMo models."""

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
        import time  # noqa: PLC0415

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
        self._device = await loop.run_in_executor(
            self._executor,
            _load_model_in_subprocess,
            self._resolved_model,
            self._config.device,
        )

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
        logger.debug(
            "Shutting down NeMo subprocess for model %s",
            self._config.model_name,
        )
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._executor = None
        self._device = None
        logger.info("Model %s unloaded (subprocess terminated)", self._config.model_name)

    async def transcribe(
        self,
        audio: bytes,
        *,
        source_filename: str | None = None,  # noqa: ARG002
        language: str | None = None,
        task: Literal["transcribe", "translate"] = "transcribe",
        initial_prompt: str | None = None,  # noqa: ARG002
        temperature: float = 0.0,  # noqa: ARG002
        vad_filter: bool = True,  # noqa: ARG002
        word_timestamps: bool = False,
    ) -> TranscriptionResult:
        """Transcribe audio using NeMo in subprocess."""
        if self._executor is None:
            msg = "Model not loaded. Call load() first."
            raise RuntimeError(msg)

        if task == "translate":
            logger.warning(
                "Task=translate requested for NeMo backend; using transcription output as-is",
            )

        kwargs: dict[str, Any] = {
            "language": language,
            "word_timestamps": word_timestamps,
        }

        loop = asyncio.get_running_loop()
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
