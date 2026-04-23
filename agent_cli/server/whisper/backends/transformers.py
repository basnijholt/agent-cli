"""Transformers ASR backend for HuggingFace models with safetensors support."""

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
    UnsupportedRequestError,
)

logger = logging.getLogger(__name__)

# Model name mapping: canonical name -> HuggingFace repo
_MODEL_MAP: dict[str, str] = {
    "tiny": "openai/whisper-tiny",
    "tiny.en": "openai/whisper-tiny.en",
    "base": "openai/whisper-base",
    "base.en": "openai/whisper-base.en",
    "small": "openai/whisper-small",
    "small.en": "openai/whisper-small.en",
    "medium": "openai/whisper-medium",
    "medium.en": "openai/whisper-medium.en",
    "large": "openai/whisper-large",
    "large-v2": "openai/whisper-large-v2",
    "large-v3": "openai/whisper-large-v3",
    "large-v3-turbo": "openai/whisper-large-v3-turbo",
    "turbo": "openai/whisper-large-v3-turbo",
    # Distil variants (smaller, faster)
    "distil-large-v2": "distil-whisper/distil-large-v2",
    "distil-large-v3": "distil-whisper/distil-large-v3",
    "distil-medium.en": "distil-whisper/distil-medium.en",
    "distil-small.en": "distil-whisper/distil-small.en",
}

_REMOTE_CODE_MODEL_PREFIXES = ("CohereLabs/cohere-transcribe",)


def _resolve_model_name(model_name: str) -> str:
    """Resolve a model name to a HuggingFace repo."""
    if "/" in model_name:
        return model_name
    return _MODEL_MAP.get(model_name, f"openai/whisper-{model_name}")


def requires_remote_code(model_name: str) -> bool:
    """Return True for transformers ASR models this backend trusts by default."""
    resolved_model = _resolve_model_name(model_name)
    return resolved_model.startswith(_REMOTE_CODE_MODEL_PREFIXES)


def _is_cohere_asr_model() -> bool:
    """Return True when the loaded model is Cohere ASR."""
    return _state.is_cohere_asr


def download_model(model_name: str, cache_dir: Path | None = None) -> str:
    """Download a Whisper model from the HuggingFace Hub.

    Returns the resolved repo name.
    """
    from huggingface_hub import snapshot_download  # noqa: PLC0415

    resolved_model = _resolve_model_name(model_name)
    snapshot_download(
        repo_id=resolved_model,
        cache_dir=str(cache_dir) if cache_dir else None,
    )
    return resolved_model


# --- Subprocess state (only used within subprocess worker) ---


@dataclass
class _SubprocessState:
    """Container for subprocess-local state. Not shared with main process."""

    model: Any = None
    processor: Any = None
    model_name: str | None = None
    dtype: Any = None
    device: str | None = None
    is_cohere_asr: bool = False
    has_transcribe_helper: bool = False


_state = _SubprocessState()


# --- Subprocess worker functions (run in isolated process) ---


def _load_model_in_subprocess(
    model_name: str,
    device: str,
    download_root: str | None,
    trust_remote_code: bool,
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

    allow_remote_code = trust_remote_code or requires_remote_code(model_name)

    _state.processor = AutoProcessor.from_pretrained(
        model_name,
        cache_dir=download_root,
        trust_remote_code=allow_remote_code,
    )
    dtype = torch.float16 if device != "cpu" else torch.float32
    _state.model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_name,
        cache_dir=download_root,
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
        trust_remote_code=allow_remote_code,
    )
    _state.model.to(device)
    _state.model.eval()
    _state.model_name = model_name
    _state.dtype = dtype
    _state.device = device
    _state.is_cohere_asr = requires_remote_code(model_name)
    _state.has_transcribe_helper = hasattr(_state.model, "transcribe")

    return device


def _read_wav_audio(wav_path: str) -> tuple[Any, int, float]:
    """Read a WAV file into a float32 numpy array."""
    import numpy as np  # noqa: PLC0415

    with wave.open(wav_path, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        audio_bytes = wav_file.readframes(wav_file.getnframes())
        duration = wav_file.getnframes() / sample_rate

    audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    return audio_array, sample_rate, duration


def _make_result(
    *,
    text: str,
    language: str,
    language_probability: float,
    duration: float,
    supports_segments: bool = False,
) -> dict[str, Any]:
    """Build the serialized transcription result returned from the subprocess."""
    return {
        "text": text.strip(),
        "language": language,
        "language_probability": language_probability,
        "duration": duration,
        "segments": [],
        "supports_segments": supports_segments,
    }


def _move_inputs_to_device(inputs: Any) -> Any:
    """Move processor inputs to the loaded model device."""
    if hasattr(inputs, "to"):
        if _state.dtype is None:
            return inputs.to(_state.device)
        return inputs.to(_state.device, dtype=_state.dtype)
    return {k: v.to(_state.device) if hasattr(v, "to") else v for k, v in inputs.items()}


def _transcribe_cohere_asr(
    *,
    audio_array: Any,
    sample_rate: int,
    effective_language: str | None,
    task: str,
    duration: float,
) -> dict[str, Any]:
    """Transcribe with Cohere ASR's documented processor/generate/decode flow."""
    if not effective_language:
        msg = (
            "This model requires a language code. Pass `language` in the request "
            "or start the server with `--default-language`."
        )
        raise UnsupportedRequestError(msg)
    if task != "transcribe":
        msg = "Translation is not supported by this model."
        raise UnsupportedRequestError(msg)

    import torch  # noqa: PLC0415

    inputs = _state.processor(
        audio=audio_array,
        sampling_rate=sample_rate,
        return_tensors="pt",
        language=effective_language,
    )
    audio_chunk_index = inputs.get("audio_chunk_index")
    inputs = _move_inputs_to_device(inputs)

    with torch.no_grad():
        generated_ids = _state.model.generate(**inputs, max_new_tokens=256)
        text = _state.processor.decode(
            generated_ids,
            skip_special_tokens=True,
            audio_chunk_index=audio_chunk_index,
            language=effective_language,
        )
    if isinstance(text, list):
        text = text[0] if text else ""

    return _make_result(
        text=text,
        language=effective_language,
        language_probability=1.0,
        duration=duration,
    )


def _transcribe_with_model_helper(
    *,
    audio_array: Any,
    sample_rate: int,
    effective_language: str | None,
    task: str,
    duration: float,
) -> dict[str, Any]:
    """Transcribe with a custom model-level transcribe helper."""
    if task != "transcribe":
        msg = "Translation is not supported by this model."
        raise UnsupportedRequestError(msg)

    texts = _state.model.transcribe(
        processor=_state.processor,
        audio_arrays=[audio_array],
        sample_rates=[sample_rate],
        language=effective_language,
    )
    text = texts[0] if texts else ""
    return _make_result(
        text=text,
        language=effective_language or "unknown",
        language_probability=1.0 if effective_language else 0.0,
        duration=duration,
    )


def _transcribe_with_generate(
    *,
    audio_array: Any,
    sample_rate: int,
    effective_language: str | None,
    task: str,
    initial_prompt: str | None,
    beam_size: int,
    duration: float,
) -> dict[str, Any]:
    """Transcribe with the standard Whisper generate path."""
    import torch  # noqa: PLC0415

    audio_tensor = torch.from_numpy(audio_array)
    inputs = _state.processor(
        audio_tensor,
        sampling_rate=sample_rate,
        return_tensors="pt",
    )
    inputs = {k: v.to(_state.device) for k, v in inputs.items()}

    generate_args: dict[str, Any] = {
        **inputs,
        "num_beams": beam_size,
        "task": task,
        "return_timestamps": False,
    }

    if "attention_mask" not in generate_args:
        generate_args["attention_mask"] = inputs.get(
            "attention_mask",
            torch.ones_like(inputs["input_features"][:, 0, :]),
        )

    if effective_language:
        generate_args["language"] = effective_language

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

    return _make_result(
        text=text,
        language=effective_language or "en",
        language_probability=1.0 if effective_language else 0.95,
        duration=duration,
    )


def _transcribe_in_subprocess(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Run transcription in subprocess. Reuses model from _state."""
    if _state.model is None or _state.processor is None:
        msg = "Model not loaded in subprocess. Call _load_model_in_subprocess first."
        raise RuntimeError(msg)

    audio_array, sample_rate, duration = _read_wav_audio(kwargs.pop("wav_path"))
    effective_language = kwargs.get("language") or kwargs.get("default_language")
    task = kwargs.get("task", "transcribe")

    if _is_cohere_asr_model():
        return _transcribe_cohere_asr(
            audio_array=audio_array,
            sample_rate=sample_rate,
            effective_language=effective_language,
            task=task,
            duration=duration,
        )

    if _state.has_transcribe_helper:
        return _transcribe_with_model_helper(
            audio_array=audio_array,
            sample_rate=sample_rate,
            effective_language=effective_language,
            task=task,
            duration=duration,
        )

    return _transcribe_with_generate(
        audio_array=audio_array,
        sample_rate=sample_rate,
        effective_language=effective_language,
        task=task,
        initial_prompt=kwargs.get("initial_prompt"),
        beam_size=kwargs.get("beam_size", 5),
        duration=duration,
    )


class TransformersWhisperBackend:
    """ASR backend using HuggingFace transformers.

    Supports loading Whisper checkpoints and remote-code ASR models.
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
            self._config.trust_remote_code,
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
            "default_language": self._config.default_language,
            "task": task,
            "initial_prompt": initial_prompt,
        }

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                self._executor,
                _transcribe_in_subprocess,
                kwargs,
            )
        finally:
            await asyncio.to_thread(Path(tmp_path).unlink, missing_ok=True)

        return TranscriptionResult(
            text=result["text"],
            language=result["language"],
            language_probability=result["language_probability"],
            duration=result["duration"],
            segments=result["segments"],
            supports_segments=result["supports_segments"],
        )
