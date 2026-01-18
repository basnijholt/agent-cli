"""Kokoro TTS backend using PyTorch-based synthesis."""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from multiprocessing import Manager, get_context
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent_cli import constants
from agent_cli.core.process import set_process_title
from agent_cli.server.streaming import AsyncQueueReader, QueueWriter
from agent_cli.server.tts.backends.base import (
    BackendConfig,
    InvalidTextError,
    SynthesisResult,
    get_backend_cache_dir,
    get_torch_device,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

# HuggingFace repository for Kokoro model and voices
KOKORO_HF_REPO = "hexgrad/Kokoro-82M"

# Default voice if none specified
DEFAULT_VOICE = "af_heart"


# --- Subprocess state (only used within subprocess worker) ---
# This state persists across function calls within the subprocess because:
# 1. Model loading is expensive and must be reused across synthesis calls
# 2. PyTorch models cannot be pickled/passed through IPC queues
# 3. The subprocess is long-lived (ProcessPoolExecutor reuses workers)


@dataclass
class _SubprocessState:
    """Container for subprocess-local state. Not shared with main process."""

    model: Any = None
    device: str | None = None
    pipelines: dict[str, Any] = field(default_factory=dict)


_state = _SubprocessState()


# --- Subprocess worker functions (run in isolated process) ---


def _hf_download(filename: str, local_dir: Path) -> Path:
    """Download a file from Kokoro HuggingFace repo."""
    from huggingface_hub import hf_hub_download  # noqa: PLC0415

    local_dir.mkdir(parents=True, exist_ok=True)
    hf_hub_download(repo_id=KOKORO_HF_REPO, filename=filename, local_dir=local_dir)
    return local_dir / Path(filename).name


def _ensure_model(cache_dir: Path) -> Path:
    """Ensure model and config exist, downloading if needed."""
    model_dir = cache_dir / "model"
    model_path = model_dir / "kokoro-v1_0.pth"
    config_path = model_dir / "config.json"

    if not model_path.exists():
        logger.info("Downloading Kokoro model...")
        _hf_download("kokoro-v1_0.pth", model_dir)
    if not config_path.exists():
        logger.info("Downloading Kokoro config...")
        _hf_download("config.json", model_dir)

    return model_path


def _ensure_voice(voice_name: str, cache_dir: Path) -> Path:
    """Ensure voice file exists, downloading if needed."""
    voice_path = cache_dir / "voices" / f"{voice_name}.pt"
    if not voice_path.exists():
        logger.info("Downloading voice '%s'...", voice_name)
        # HuggingFace downloads to local_dir/filename, so pass cache_dir (not cache_dir/voices)
        _hf_download(f"voices/{voice_name}.pt", cache_dir)
    return voice_path


def _resolve_model_path(model_name: str, cache_dir: Path) -> Path:
    """Resolve model path, downloading if necessary."""
    # Explicit path to existing file
    path = Path(model_name)
    if path.exists() and path.suffix == ".pth":
        return path

    # Otherwise download from HuggingFace
    return _ensure_model(cache_dir)


def _resolve_voice_path(voice: str | None, cache_dir: Path) -> tuple[str, str]:
    """Resolve voice name to path and determine language code."""
    voice_name = voice or DEFAULT_VOICE

    # Explicit path to existing file
    path = Path(voice_name)
    if path.exists() and path.suffix == ".pt":
        # Kokoro convention: first letter of voice name = language code (a=American, b=British, etc.)
        return str(path), path.stem[0].lower()

    # Download from HuggingFace if needed
    voice_path = _ensure_voice(voice_name, cache_dir)
    return str(voice_path), voice_name[0].lower()


def _get_pipeline(voice: str | None, cache_dir: str) -> tuple[Any, str]:
    """Get or create pipeline for the given voice. Returns (pipeline, voice_path)."""
    from kokoro import KPipeline  # noqa: PLC0415

    cache_path = Path(cache_dir)
    voice_path, lang_code = _resolve_voice_path(voice, cache_path)

    if lang_code not in _state.pipelines:
        _state.pipelines[lang_code] = KPipeline(
            lang_code=lang_code,
            model=_state.model,
            device=_state.device,
        )

    return _state.pipelines[lang_code], voice_path


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

    # Resolve model path (downloads if needed)
    model_path = _resolve_model_path(model_name, cache_path)
    config_path = model_path.parent / "config.json"

    # Determine actual device
    if device == "auto":
        device = get_torch_device()

    # Load and move model to device
    model = KModel(config=str(config_path), model=str(model_path)).eval()
    if device == "cuda":
        model = model.cuda()
    elif device == "mps":
        model = model.to(torch.device("mps"))

    # Store in subprocess state for reuse
    _state.model = model
    _state.device = device
    _state.pipelines = {}

    # Warmup pipeline for default language
    lang = DEFAULT_VOICE[0]
    logger.info("Warming up pipeline for lang_code '%s'...", lang)
    _state.pipelines[lang] = KPipeline(lang_code=lang, model=model, device=device)

    return device


def _synthesize_in_subprocess(
    text: str,
    voice: str | None,
    speed: float,
    cache_dir: str,
) -> dict[str, Any]:
    """Synthesize text to audio in subprocess."""
    import numpy as np  # noqa: PLC0415

    pipeline, voice_path = _get_pipeline(voice, cache_dir)

    # Synthesize and collect audio chunks
    audio_chunks = [
        r.audio.numpy()
        for r in pipeline(text, voice=voice_path, speed=speed, model=_state.model)
        if r.audio is not None
    ]
    if not audio_chunks:
        msg = "No audio generated"
        raise RuntimeError(msg)

    # Convert to int16 WAV
    audio = np.concatenate(audio_chunks)
    audio_int16 = (audio * 32767).astype(np.int16)

    sample_rate = constants.KOKORO_DEFAULT_SAMPLE_RATE
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio_int16.tobytes())

    return {
        "audio": buffer.getvalue(),
        "sample_rate": sample_rate,
        "duration": len(audio_int16) / sample_rate,
    }


def _synthesize_stream_in_subprocess(
    text: str,
    voice: str | None,
    speed: float,
    cache_dir: str,
    output_queue: Any,  # Manager queue proxy
) -> None:
    """Stream audio chunks through queue as Kokoro generates them."""
    import numpy as np  # noqa: PLC0415

    writer = QueueWriter(output_queue)

    try:
        pipeline, voice_path = _get_pipeline(voice, cache_dir)

        chunk_count = 0
        total_samples = 0

        for result in pipeline(text, voice=voice_path, speed=speed, model=_state.model):
            if result.audio is not None:
                # Convert to int16 PCM bytes
                audio_int16 = (result.audio.numpy() * 32767).astype(np.int16)
                writer.send_data(audio_int16.tobytes())
                chunk_count += 1
                total_samples += len(audio_int16)

        sample_rate = constants.KOKORO_DEFAULT_SAMPLE_RATE
        writer.send_done(
            {
                "chunk_count": chunk_count,
                "total_samples": total_samples,
                "duration": total_samples / sample_rate,
                "sample_rate": sample_rate,
            },
        )

    except Exception as e:
        writer.send_error(e)


class KokoroBackend:
    """Kokoro TTS backend with subprocess isolation.

    Uses kokoro library for high-quality neural TTS on CUDA, MPS, or CPU.
    Models and voices auto-download from HuggingFace on first use.
    Subprocess terminates on unload, releasing all GPU/CPU memory.
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
            self._config.model_name,
            self._config.device,
            str(self._cache_dir),
        )

        load_duration = time.time() - start_time
        logger.info("Loaded Kokoro model on %s in %.2fs", self._device, load_duration)
        return load_duration

    async def unload(self) -> None:
        """Shutdown subprocess, releasing all memory."""
        if self._executor is None:
            return
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
        """Synthesize text to audio."""
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
            sample_width=2,
            channels=1,
            duration=result["duration"],
        )

    @property
    def supports_streaming(self) -> bool:
        """Kokoro backend supports streaming synthesis."""
        return True

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        speed: float = 1.0,
    ) -> AsyncIterator[bytes]:
        """Stream synthesized audio chunks as they are generated."""
        if self._executor is None:
            msg = "Model not loaded. Call load() first."
            raise RuntimeError(msg)

        if not text or not text.strip():
            msg = "Text cannot be empty"
            raise InvalidTextError(msg)

        # Use Manager queue for cross-process communication
        # Manager queues work with already-running subprocesses
        manager = Manager()
        try:
            queue = manager.Queue(maxsize=10)  # Backpressure control
            loop = asyncio.get_running_loop()

            # Submit streaming worker to subprocess
            # Manager queue is a proxy that works with already-running subprocesses
            future = loop.run_in_executor(
                self._executor,
                _synthesize_stream_in_subprocess,
                text,
                voice,
                speed,
                str(self._cache_dir),
                queue,  # type: ignore[arg-type]
            )

            # Yield chunks as they arrive
            reader = AsyncQueueReader(queue, timeout=30.0)  # type: ignore[arg-type]
            async for chunk in reader:
                if chunk.chunk_type == "done":
                    break
                if chunk.chunk_type == "error":
                    msg = str(chunk.payload)
                    raise RuntimeError(msg)
                if chunk.payload is not None:
                    yield chunk.payload  # type: ignore[misc]

            # Ensure subprocess completes
            await future
        finally:
            manager.shutdown()
