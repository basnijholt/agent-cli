"""Qwen3-TTS backend using qwen-tts library with subprocess isolation."""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from multiprocessing import get_context
from typing import Any, NoReturn

from agent_cli.core.process import set_process_title
from agent_cli.server.tts.backends.base import (
    BackendConfig,
    InvalidTextError,
    SynthesisResult,
    get_backend_cache_dir,
    get_torch_device,
)
from agent_cli.services import pcm_to_wav

logger = logging.getLogger(__name__)

# Default model for Qwen3-TTS
DEFAULT_QWEN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"

# Default voice if none specified
DEFAULT_VOICE = "Vivian"

# Voice name mapping: OpenAI-style names -> Qwen speaker names
# Qwen supports: Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee
VOICE_MAP = {
    # OpenAI-compatible names
    "alloy": "Vivian",
    "echo": "Ryan",
    "fable": "Serena",
    "onyx": "Uncle_Fu",
    "nova": "Dylan",
    "shimmer": "Ono_Anna",
    # Direct Qwen names (pass-through)
    "vivian": "Vivian",
    "serena": "Serena",
    "uncle_fu": "Uncle_Fu",
    "dylan": "Dylan",
    "eric": "Eric",
    "ryan": "Ryan",
    "aiden": "Aiden",
    "ono_anna": "Ono_Anna",
    "sohee": "Sohee",
}


# --- Subprocess state (only used within subprocess worker) ---


@dataclass
class _SubprocessState:
    """Container for subprocess-local state. Not shared with main process."""

    model: Any = None
    device: str | None = None
    model_name: str | None = None


_state = _SubprocessState()


# --- Subprocess worker functions (run in isolated process) ---


def _load_model_in_subprocess(
    model_name: str,
    device: str,
    cache_dir: str,
) -> str:
    """Load Qwen3-TTS model in subprocess. Returns actual device string."""
    import torch  # noqa: PLC0415
    from qwen_tts import Qwen3TTSModel  # noqa: PLC0415

    set_process_title("tts-qwen")

    # Determine actual device
    if device == "auto":
        device = get_torch_device()

    # Determine dtype based on device
    dtype = torch.bfloat16 if device in ("cuda", "mps") else torch.float32

    logger.info("Loading Qwen3-TTS model '%s' on %s...", model_name, device)

    # Build kwargs for model loading
    load_kwargs: dict[str, Any] = {
        "dtype": dtype,
    }

    # Add device_map for CUDA/MPS/CPU
    if device == "cuda":
        load_kwargs["device_map"] = "cuda:0"
    elif device == "mps":
        load_kwargs["device_map"] = "mps"
    else:
        load_kwargs["device_map"] = "cpu"

    # Load model
    model = Qwen3TTSModel.from_pretrained(model_name, cache_dir=cache_dir, **load_kwargs)

    # Store in subprocess state for reuse
    _state.model = model
    _state.device = device
    _state.model_name = model_name

    # Enable optimizations for CUDA
    if device == "cuda" and torch.cuda.is_available():
        torch.backends.cudnn.benchmark = True
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        logger.info("Enabled CUDA optimizations (cuDNN benchmark, TF32)")

    return device


def _synthesize_in_subprocess(
    text: str,
    voice: str | None,
    language: str,
    speed: float,
) -> dict[str, Any]:
    """Synthesize text to audio in subprocess."""
    import numpy as np  # noqa: PLC0415

    if _state.model is None:
        msg = "Model not loaded in subprocess"
        raise RuntimeError(msg)

    # Map voice name
    voice_name = voice or DEFAULT_VOICE
    voice_lower = voice_name.lower()
    speaker = VOICE_MAP.get(voice_lower, voice_name)

    # Generate speech
    wavs, sr = _state.model.generate_custom_voice(
        text=text,
        language=language,
        speaker=speaker,
    )

    if not wavs or len(wavs) == 0:
        msg = "No audio generated"
        raise RuntimeError(msg)

    audio = wavs[0]

    # Apply speed adjustment if needed
    if speed != 1.0:
        import librosa  # noqa: PLC0415

        audio = librosa.effects.time_stretch(audio.astype(np.float32), rate=speed)

    # Convert to int16 WAV using existing helper
    audio_int16 = (audio * 32767).astype(np.int16)
    wav_bytes = pcm_to_wav(audio_int16.tobytes(), sample_rate=sr)

    return {
        "audio": wav_bytes,
        "sample_rate": sr,
        "duration": len(audio_int16) / sr,
    }


class QwenBackend:
    """Qwen3-TTS backend with subprocess isolation.

    Uses qwen-tts library for high-quality multilingual neural TTS on CUDA, MPS, or CPU.
    Models auto-download from HuggingFace on first use.
    Subprocess terminates on unload, releasing all GPU/CPU memory.

    Features:
    - 9 premium voices with various gender, age, language combinations
    - 10+ language support (Chinese, English, Japanese, Korean, German, French, etc.)
    - Natural language instruction control (for CustomVoice model)
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the Qwen backend."""
        self._config = config
        self._executor: ProcessPoolExecutor | None = None
        self._device: str | None = None
        self._cache_dir = config.cache_dir or get_backend_cache_dir("qwen-tts")
        # Use provided model name or default - "qwen" is the CLI placeholder for default
        model_name = config.model_name
        if not model_name or model_name == "qwen":
            model_name = DEFAULT_QWEN_MODEL
        self._model_name = model_name

    @property
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        return self._executor is not None

    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on."""
        return self._device

    async def load(self) -> float:
        """Load model in subprocess. Downloads from HuggingFace if needed."""
        if self._executor is not None:
            return 0.0

        start_time = time.time()
        ctx = get_context("spawn")
        self._executor = ProcessPoolExecutor(max_workers=1, mp_context=ctx)

        loop = asyncio.get_running_loop()
        self._device = await loop.run_in_executor(
            self._executor,
            _load_model_in_subprocess,
            self._model_name,
            self._config.device,
            str(self._cache_dir),
        )

        load_duration = time.time() - start_time
        logger.info("Loaded Qwen3-TTS model on %s in %.2fs", self._device, load_duration)
        return load_duration

    async def unload(self) -> None:
        """Shutdown subprocess, releasing all memory."""
        if self._executor is None:
            return
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._executor = None
        self._device = None
        logger.info("Qwen3-TTS model unloaded (subprocess terminated)")

    async def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float = 1.0,
        language: str = "Auto",
    ) -> SynthesisResult:
        """Synthesize text to audio.

        Args:
            text: Text to synthesize.
            voice: Voice to use (e.g., "Vivian", "Ryan", or OpenAI names like "alloy").
            speed: Speech speed multiplier (0.25 to 4.0).
            language: Language hint (Auto, English, Chinese, Japanese, etc.).

        Returns:
            SynthesisResult with audio data and metadata.

        """
        if self._executor is None:
            msg = "Model not loaded. Call load() first."
            raise RuntimeError(msg)

        if not text or not text.strip():
            msg = "Text cannot be empty"
            raise InvalidTextError(msg)

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            self._executor,
            _synthesize_in_subprocess,
            text,
            voice,
            language,
            speed,
        )

        return SynthesisResult(
            audio=result["audio"],
            sample_rate=result["sample_rate"],
            sample_width=2,
            channels=1,
            duration=result["duration"],
        )

    @property
    def supports_streaming(self) -> bool:
        """Qwen3-TTS backend does not currently support streaming synthesis."""
        return False

    def synthesize_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> NoReturn:
        """Streaming is not currently supported by Qwen3-TTS backend."""
        msg = "Streaming synthesis is not yet supported by Qwen3-TTS backend"
        raise NotImplementedError(msg)
