"""Kokoro TTS backend using PyTorch-based synthesis."""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_cli import constants
from agent_cli.server.tts.backends.base import (
    BackendConfig,
    InvalidTextError,
    SynthesisResult,
    get_backend_cache_dir,
)

if TYPE_CHECKING:
    from kokoro import KModel, KPipeline

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


def _load_model_sync(
    model_path: str,
    device: str,
) -> tuple[Any, Any]:
    """Load Kokoro model synchronously."""
    from kokoro import KModel  # noqa: PLC0415

    config_path = Path(model_path).parent / "config.json"
    if not config_path.exists():
        msg = f"Kokoro config not found: {config_path}"
        raise FileNotFoundError(msg)

    model = KModel(config=str(config_path), model=model_path).eval()

    # Move model to appropriate device
    import torch  # noqa: PLC0415

    if device == "cuda":
        model = model.cuda()
    elif device == "mps":
        model = model.to(torch.device("mps"))
    else:
        model = model.cpu()

    return model, device


def _synthesize_sync(
    model: KModel,
    pipeline: KPipeline,
    text: str,
    voice_path: str,
    speed: float,
    sample_rate: int,
) -> tuple[bytes, float]:
    """Synthesize text to audio synchronously."""
    import numpy as np  # noqa: PLC0415

    # Collect all audio chunks
    audio_chunks: list[np.ndarray] = [
        result.audio.numpy()
        for result in pipeline(text, voice=voice_path, speed=speed, model=model)
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
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())

    audio_data = buffer.getvalue()

    # Calculate duration
    duration = len(audio_int16) / sample_rate

    return audio_data, duration


class KokoroBackend:
    """Kokoro TTS backend using PyTorch-based synthesis.

    This backend uses the kokoro library for high-quality neural TTS.
    Supports CUDA, MPS (Apple Silicon), and CPU inference.

    Models and voices are automatically downloaded from HuggingFace on first use.
    """

    def __init__(self, config: BackendConfig) -> None:
        """Initialize the Kokoro backend."""
        self._config = config
        self._model: KModel | None = None
        self._pipelines: dict[str, KPipeline] = {}  # Pipelines by lang_code
        self._sample_rate: int = constants.KOKORO_DEFAULT_SAMPLE_RATE
        self._device: str | None = None
        self._cache_dir = config.cache_dir or get_backend_cache_dir("kokoro")

    @property
    def is_loaded(self) -> bool:
        """Check if the model is currently loaded."""
        return self._model is not None

    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on, or None if not loaded."""
        return self._device

    def _get_pipeline(self, lang_code: str) -> KPipeline:
        """Get or create pipeline for language code."""
        from kokoro import KPipeline  # noqa: PLC0415

        if lang_code not in self._pipelines:
            logger.debug("Creating Kokoro pipeline for lang_code: %s", lang_code)
            self._pipelines[lang_code] = KPipeline(
                lang_code=lang_code,
                model=self._model,
                device=self._device,
            )
        return self._pipelines[lang_code]

    def _resolve_model_path(self) -> Path:
        """Resolve model path, downloading if necessary."""
        model_name = self._config.model_name

        # Check if it's "auto" or a known model name
        if model_name in ("auto", "kokoro", "kokoro-v1_0"):
            # Auto-download from HuggingFace
            return _download_model_sync(self._cache_dir)

        # Check if it's already a valid path
        model_path = Path(model_name)
        if model_path.exists() and model_path.suffix == ".pth":
            return model_path

        # Try to find in cache
        cached_path = self._cache_dir / "model" / f"{model_name}.pth"
        if cached_path.exists():
            return cached_path

        # Default to auto-download
        return _download_model_sync(self._cache_dir)

    def _resolve_voice_path(self, voice: str | None) -> tuple[str, str]:
        """Resolve voice name to path and determine language code.

        Auto-downloads voice from HuggingFace if not present.
        """
        voice_name = voice or DEFAULT_VOICE

        # Check if it's already a path
        voice_path = Path(voice_name)
        if voice_path.exists() and voice_path.suffix == ".pt":
            lang_code = voice_path.stem[0].lower()
            return str(voice_path), lang_code

        # Look for voice file in cache, download if not present
        voices_dir = self._cache_dir / "voices"
        voice_file = voices_dir / f"{voice_name}.pt"

        if not voice_file.exists():
            # Try to download from HuggingFace
            if voice_name in KOKORO_VOICES:
                voice_file = _download_voice_sync(voice_name, self._cache_dir)
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

    async def load(self) -> float:
        """Load the model into memory.

        Automatically downloads from HuggingFace if not present.
        """
        if self._model is not None:
            return 0.0

        start_time = time.time()

        # Determine device
        target_device = self._config.device
        if target_device == "auto":
            target_device = _get_device()

        # Resolve model path (may trigger download)
        loop = asyncio.get_running_loop()
        model_path = await loop.run_in_executor(None, self._resolve_model_path)

        # Load model in executor
        model, device = await loop.run_in_executor(
            None,
            _load_model_sync,
            str(model_path),
            target_device,
        )

        self._model = model
        self._device = device

        # Warmup: create pipeline for default voice language
        # This triggers spacy model download if needed
        default_lang = DEFAULT_VOICE[0]  # 'a' from 'af_heart'
        logger.info("Warming up pipeline for lang_code '%s'...", default_lang)
        self._get_pipeline(default_lang)

        load_duration = time.time() - start_time
        logger.info(
            "Loaded Kokoro model on %s in %.2fs",
            self._device,
            load_duration,
        )

        return load_duration

    async def unload(self) -> None:
        """Unload the model and free memory."""
        if self._model is not None:
            logger.info("Unloading Kokoro model")

            # Clear pipelines
            self._pipelines.clear()

            # Delete model
            del self._model
            self._model = None

            # Clear GPU memory if applicable
            import torch  # noqa: PLC0415

            device = self._device
            self._device = None

            if device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            elif device == "mps" and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()

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
        if self._model is None:
            msg = "Model not loaded"
            raise RuntimeError(msg)

        if not text or not text.strip():
            msg = "Text cannot be empty"
            raise InvalidTextError(msg)

        # Resolve voice path and language code (may trigger download)
        loop = asyncio.get_running_loop()
        voice_path, lang_code = await loop.run_in_executor(
            None,
            self._resolve_voice_path,
            voice,
        )

        # Get or create pipeline for this language
        pipeline = self._get_pipeline(lang_code)

        # Run synthesis in executor
        audio_data, duration = await loop.run_in_executor(
            None,
            _synthesize_sync,
            self._model,
            pipeline,
            text,
            voice_path,
            speed,
            self._sample_rate,
        )

        return SynthesisResult(
            audio=audio_data,
            sample_rate=self._sample_rate,
            sample_width=2,  # 16-bit
            channels=1,  # Mono
            duration=duration,
        )
