"""Kokoro TTS backend using PyTorch-based synthesis."""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from typing import Any

from agent_cli import constants
from agent_cli.core.process import set_process_title
from agent_cli.server.tts.backends.base import (
    BackendConfig,
    InvalidTextError,
    SynthesisResult,
    get_backend_cache_dir,
)

logger = logging.getLogger(__name__)

# HuggingFace repository for Kokoro model and voices
KOKORO_HF_REPO = "hexgrad/Kokoro-82M"
KOKORO_MODEL_FILE = "kokoro-v1_0.pth"
KOKORO_CONFIG_FILE = "config.json"

# Available voices (first letter indicates language: a=American, b=British, etc.)
KOKORO_VOICES = [
    # American Female
    "af_alloy",
    "af_aoede",
    "af_bella",
    "af_heart",
    "af_jessica",
    "af_kore",
    "af_nicole",
    "af_nova",
    "af_river",
    "af_sarah",
    "af_sky",
    # American Male
    "am_adam",
    "am_echo",
    "am_eric",
    "am_fenrir",
    "am_liam",
    "am_michael",
    "am_onyx",
    "am_puck",
    # British Female
    "bf_alice",
    "bf_emma",
    "bf_isabella",
    "bf_lily",
    # British Male
    "bm_daniel",
    "bm_fable",
    "bm_george",
    "bm_lewis",
]

# Default voice if none specified
DEFAULT_VOICE = "af_heart"

# --- Subprocess globals (only used within subprocess worker) ---
# These are initialized by _load_model_in_subprocess and used by _synthesize_in_subprocess
_subprocess_model: Any = None
_subprocess_device: str | None = None
_subprocess_pipelines: dict[str, Any] = {}


# --- Subprocess worker functions (run in isolated process) ---


def _get_device() -> str:
    """Detect the best available device for PyTorch."""
    import torch  # noqa: PLC0415

    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _download_model_sync(cache_dir: Path) -> Path:
    """Download Kokoro model from HuggingFace if not present."""
    from huggingface_hub import hf_hub_download  # noqa: PLC0415

    model_dir = cache_dir / "model"
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / KOKORO_MODEL_FILE
    config_path = model_dir / KOKORO_CONFIG_FILE

    # Download model if not present
    if not model_path.exists():
        logger.info("Downloading Kokoro model from HuggingFace...")
        downloaded = hf_hub_download(
            repo_id=KOKORO_HF_REPO,
            filename=KOKORO_MODEL_FILE,
            local_dir=model_dir,
        )
        logger.info("Downloaded model to %s", downloaded)

    # Download config if not present
    if not config_path.exists():
        logger.info("Downloading Kokoro config from HuggingFace...")
        downloaded = hf_hub_download(
            repo_id=KOKORO_HF_REPO,
            filename=KOKORO_CONFIG_FILE,
            local_dir=model_dir,
        )
        logger.info("Downloaded config to %s", downloaded)

    return model_path


def _download_voice_sync(voice_name: str, cache_dir: Path) -> Path:
    """Download a Kokoro voice from HuggingFace if not present."""
    from huggingface_hub import hf_hub_download  # noqa: PLC0415

    voices_dir = cache_dir / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)

    voice_file = f"voices/{voice_name}.pt"
    voice_path = voices_dir / f"{voice_name}.pt"

    if not voice_path.exists():
        logger.info("Downloading voice '%s' from HuggingFace...", voice_name)
        downloaded = hf_hub_download(
            repo_id=KOKORO_HF_REPO,
            filename=voice_file,
            local_dir=cache_dir,
        )
        logger.info("Downloaded voice to %s", downloaded)

    return voice_path


def _resolve_model_path(model_name: str, cache_dir: Path) -> Path:
    """Resolve model path, downloading if necessary."""
    # Check if it's "auto" or a known model name
    if model_name in ("auto", "kokoro", "kokoro-v1_0"):
        # Auto-download from HuggingFace
        return _download_model_sync(cache_dir)

    # Check if it's already a valid path
    model_path = Path(model_name)
    if model_path.exists() and model_path.suffix == ".pth":
        return model_path

    # Try to find in cache
    cached_path = cache_dir / "model" / f"{model_name}.pth"
    if cached_path.exists():
        return cached_path

    # Default to auto-download
    return _download_model_sync(cache_dir)


def _resolve_voice_path(voice: str | None, cache_dir: Path) -> tuple[str, str]:
    """Resolve voice name to path and determine language code."""
    voice_name = voice or DEFAULT_VOICE

    # Check if it's already a path
    voice_path = Path(voice_name)
    if voice_path.exists() and voice_path.suffix == ".pt":
        lang_code = voice_path.stem[0].lower()
        return str(voice_path), lang_code

    # Look for voice file in cache, download if not present
    voices_dir = cache_dir / "voices"
    voice_file = voices_dir / f"{voice_name}.pt"

    if not voice_file.exists():
        # Try to download from HuggingFace
        if voice_name in KOKORO_VOICES:
            voice_file = _download_voice_sync(voice_name, cache_dir)
        # Check if it exists locally anyway
        elif not voice_file.exists():
            available = ", ".join(KOKORO_VOICES[:5]) + "..."
            msg = (
                f"Voice '{voice_name}' not found. "
                f"Available voices: {available}. "
                f"See full list at https://huggingface.co/hexgrad/Kokoro-82M"
            )
            raise FileNotFoundError(msg)

    # Lang code is first letter of voice name
    lang_code = voice_name[0].lower()
    return str(voice_file), lang_code


def _load_model_in_subprocess(
    model_name: str,
    device: str,
    cache_dir: str,
) -> str:
    """Load Kokoro model in subprocess. Returns actual device string."""
    import torch  # noqa: PLC0415
    from kokoro import KModel, KPipeline  # noqa: PLC0415

    set_process_title("tts-kokoro")

    cache_path = Path(cache_dir)

    # Resolve and download model if needed
    model_path = _resolve_model_path(model_name, cache_path)
    config_path = model_path.parent / "config.json"

    if not config_path.exists():
        msg = f"Kokoro config not found: {config_path}"
        raise FileNotFoundError(msg)

    # Determine actual device
    if device == "auto":
        device = _get_device()

    # Load model
    model = KModel(config=str(config_path), model=str(model_path)).eval()

    # Move model to appropriate device
    if device == "cuda":
        model = model.cuda()
    elif device == "mps":
        model = model.to(torch.device("mps"))
    else:
        model = model.cpu()

    # Store model globally for reuse in synthesis calls
    global _subprocess_model, _subprocess_device, _subprocess_pipelines
    _subprocess_model = model
    _subprocess_device = device
    _subprocess_pipelines = {}

    # Warmup: create pipeline for default voice language
    default_lang = DEFAULT_VOICE[0]  # 'a' from 'af_heart'
    logger.info("Warming up pipeline for lang_code '%s'...", default_lang)
    _subprocess_pipelines[default_lang] = KPipeline(
        lang_code=default_lang,
        model=model,
        device=device,
    )

    return device


def _synthesize_in_subprocess(
    text: str,
    voice: str | None,
    speed: float,
    cache_dir: str,
) -> dict[str, Any]:
    """Synthesize text to audio in subprocess. Model stays loaded between calls."""
    import numpy as np  # noqa: PLC0415
    from kokoro import KPipeline  # noqa: PLC0415

    global _subprocess_model, _subprocess_device, _subprocess_pipelines  # noqa: PLW0602

    cache_path = Path(cache_dir)

    # Resolve voice path (may download)
    voice_path, lang_code = _resolve_voice_path(voice, cache_path)

    # Get or create pipeline for this language
    if lang_code not in _subprocess_pipelines:
        logger.debug("Creating Kokoro pipeline for lang_code: %s", lang_code)
        _subprocess_pipelines[lang_code] = KPipeline(
            lang_code=lang_code,
            model=_subprocess_model,
            device=_subprocess_device,
        )
    pipeline = _subprocess_pipelines[lang_code]

    # Collect all audio chunks
    audio_chunks: list[np.ndarray] = [
        result.audio.numpy()
        for result in pipeline(
            text,
            voice=voice_path,
            speed=speed,
            model=_subprocess_model,
        )
        if result.audio is not None
    ]

    if not audio_chunks:
        msg = "No audio generated"
        raise RuntimeError(msg)

    # Concatenate all chunks
    audio_array = np.concatenate(audio_chunks)

    # Convert float32 [-1, 1] to int16
    audio_int16 = (audio_array * 32767).astype(np.int16)

    # Create WAV buffer
    sample_rate = constants.KOKORO_DEFAULT_SAMPLE_RATE
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())

    audio_data = buffer.getvalue()

    # Calculate duration
    duration = len(audio_int16) / sample_rate

    return {
        "audio": audio_data,
        "sample_rate": sample_rate,
        "duration": duration,
    }


class KokoroBackend:
    """Kokoro TTS backend using PyTorch-based synthesis.

    This backend uses the kokoro library for high-quality neural TTS.
    Supports CUDA, MPS (Apple Silicon), and CPU inference.

    Models and voices are automatically downloaded from HuggingFace on first use.

    Uses subprocess isolation: when unloaded, the subprocess terminates
    and the OS reclaims ALL memory (GPU memory, PyTorch allocations, etc.).
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the Kokoro backend."""
        self._config = config
        self._executor: ProcessPoolExecutor | None = None
        self._device: str | None = None
        self._cache_dir = config.cache_dir or get_backend_cache_dir("kokoro")

    @property
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        return self._executor is not None

    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on, or None if not loaded."""
        return self._device

    async def load(self) -> float:
        """Load the model into memory.

        Automatically downloads from HuggingFace if not present.
        """
        if self._executor is not None:
            return 0.0

        start_time = time.time()

        logger.debug(
            "Starting Kokoro subprocess for model %s (device=%s)",
            self._config.model_name,
            self._config.device,
        )

        # Subprocess isolation: spawn context for clean state
        ctx = get_context("spawn")
        self._executor = ProcessPoolExecutor(max_workers=1, mp_context=ctx)

        loop = asyncio.get_running_loop()
        self._device = await loop.run_in_executor(
            self._executor,
            _load_model_in_subprocess,
            self._config.model_name,
            self._config.device,
            str(self._cache_dir),
        )

        load_duration = time.time() - start_time
        logger.info(
            "Loaded Kokoro model on %s in %.2fs",
            self._device,
            load_duration,
        )

        return load_duration

    async def unload(self) -> None:
        """Shutdown subprocess, releasing ALL memory."""
        if self._executor is None:
            return

        logger.debug("Shutting down Kokoro subprocess")
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._executor = None
        self._device = None
        logger.info("Kokoro model unloaded (subprocess terminated)")

    async def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> SynthesisResult:
        """Synthesize text to audio.

        Args:
            text: Text to synthesize.
            voice: Voice to use (e.g., 'af_heart', 'af_bella').
                   Auto-downloads from HuggingFace if not present.
            speed: Speech speed multiplier (0.25 to 4.0).

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
            speed,
            str(self._cache_dir),
        )

        return SynthesisResult(
            audio=result["audio"],
            sample_rate=result["sample_rate"],
            sample_width=2,  # 16-bit
            channels=1,  # Mono
            duration=result["duration"],
        )
