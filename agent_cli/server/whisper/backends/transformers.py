"""Transformers Whisper backend for HuggingFace models with safetensors support."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
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

# Model name mapping: canonical name -> HuggingFace repo
_MODEL_MAP: dict[str, str] = {
    "tiny": "openai/whisper-tiny",
    "base": "openai/whisper-base",
    "small": "openai/whisper-small",
    "medium": "openai/whisper-medium",
    "large": "openai/whisper-large",
    "large-v2": "openai/whisper-large-v2",
    "large-v3": "openai/whisper-large-v3",
    "large-v3-turbo": "openai/whisper-large-v3-turbo",
    "turbo": "openai/whisper-large-v3-turbo",
}


def _resolve_model_name(model_name: str) -> str:
    """Resolve a model name to a HuggingFace repo."""
    if "/" in model_name:
        return model_name
    return _MODEL_MAP.get(model_name, f"openai/whisper-{model_name}")


# --- Subprocess state (only used within subprocess worker) ---


@dataclass
class _SubprocessState:
    """Container for subprocess-local state. Not shared with main process."""

    model: Any = None
    processor: Any = None
    device: str | None = None


_state = _SubprocessState()


# --- Subprocess worker functions (run in isolated process) ---


def _load_model_in_subprocess(
    model_name: str,
    device: str,
    download_root: str | None,
) -> str:
    """Load model in subprocess. Returns actual device string."""
    import torch  # noqa: PLC0415
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor  # noqa: PLC0415

    set_process_title("whisper-transformers")

    # Resolve device
    if device == "auto":
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

    _state.processor = AutoProcessor.from_pretrained(
        model_name,
        cache_dir=download_root,
    )
    dtype = torch.float16 if device != "cpu" else torch.float32
    _state.model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_name,
        cache_dir=download_root,
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
    )
    _state.model.to(device)
    _state.model.eval()
    _state.device = device

    return device


def _transcribe_in_subprocess(
    audio_bytes: bytes,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Run transcription in subprocess. Reuses model from _state."""
    import torch  # noqa: PLC0415

    if _state.model is None or _state.processor is None:
        msg = "Model not loaded in subprocess. Call _load_model_in_subprocess first."
        raise RuntimeError(msg)

    # Parse WAV and extract audio
    with wave.open(kwargs.pop("wav_path"), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        audio_bytes = wav_file.readframes(wav_file.getnframes())
        duration = wav_file.getnframes() / sample_rate

    # Convert to float tensor (copy buffer to avoid non-writable tensor warning)
    import numpy as np  # noqa: PLC0415

    audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    audio_tensor = torch.from_numpy(audio_array)

    # Process audio
    inputs = _state.processor(
        audio_tensor,
        sampling_rate=sample_rate,
        return_tensors="pt",
    )
    inputs = {k: v.to(_state.device) for k, v in inputs.items()}

    language = kwargs.get("language")
    task = kwargs.get("task", "transcribe")
    initial_prompt = kwargs.get("initial_prompt")

    # Build generate arguments - use language/task directly instead of deprecated forced_decoder_ids
    generate_args: dict[str, Any] = {
        **inputs,
        "num_beams": kwargs.get("beam_size", 5),
        "task": task,
        "return_timestamps": False,
    }

    # Add attention_mask if available (avoids warning about pad token)
    if "attention_mask" not in generate_args:
        generate_args["attention_mask"] = inputs.get(
            "attention_mask",
            torch.ones_like(inputs["input_features"][:, 0, :]),
        )

    if language:
        generate_args["language"] = language

    if initial_prompt:
        prompt_ids = (
            _state.processor.tokenizer(
                initial_prompt,
                return_tensors="pt",
                add_special_tokens=False,
            )
            .input_ids[0]
            .to(_state.device)
        )
        generate_args["prompt_ids"] = prompt_ids

    with torch.no_grad():
        generated_ids = _state.model.generate(**generate_args)
        text = _state.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

    return {
        "text": text.strip(),
        "language": language or "en",
        "language_probability": 1.0 if language else 0.95,
        "duration": duration,
        "segments": [],
    }


class TransformersWhisperBackend:
    """Whisper backend using HuggingFace transformers.

    Supports loading models from safetensors format.
    Uses subprocess isolation for memory management.
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
            "Starting transformers subprocess for model %s (resolved: %s, device=%s)",
            self._config.model_name,
            self._resolved_model,
            self._config.device,
        )

        start_time = time.time()

        ctx = get_context("spawn")
        self._executor = ProcessPoolExecutor(max_workers=1, mp_context=ctx)

        download_root = str(self._config.cache_dir) if self._config.cache_dir else None
        loop = asyncio.get_running_loop()
        self._device = await loop.run_in_executor(
            self._executor,
            _load_model_in_subprocess,
            self._resolved_model,
            self._config.device,
            download_root,
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
        """Shutdown subprocess, releasing ALL memory."""
        if self._executor is None:
            return
        logger.debug(
            "Shutting down transformers subprocess for model %s",
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
        initial_prompt: str | None = None,
        temperature: float = 0.0,  # noqa: ARG002 - not used by transformers
        vad_filter: bool = True,  # noqa: ARG002 - not supported
        word_timestamps: bool = False,  # noqa: ARG002 - not supported
    ) -> TranscriptionResult:
        """Transcribe audio using transformers in subprocess."""
        if self._executor is None:
            msg = "Model not loaded. Call load() first."
            raise RuntimeError(msg)

        # Write audio to temp file for wave parsing in subprocess
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio)
            tmp_path = tmp.name

        kwargs: dict[str, Any] = {
            "wav_path": tmp_path,
            "language": language,
            "task": task,
            "initial_prompt": initial_prompt,
        }

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                self._executor,
                _transcribe_in_subprocess,
                audio,
                kwargs,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return TranscriptionResult(
            text=result["text"],
            language=result["language"],
            language_probability=result["language_probability"],
            duration=result["duration"],
            segments=result["segments"],
        )
