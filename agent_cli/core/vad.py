"""Voice Activity Detection using Silero VAD for speech segmentation.

Uses ONNX model with pure numpy inference (no torch dependency).
"""

from __future__ import annotations

import logging
import urllib.request
from collections import deque
from pathlib import Path

from agent_cli import constants

try:
    import numpy as np
    import onnxruntime
except ImportError as e:
    msg = (
        "onnxruntime is required for the transcribe-daemon command. "
        "Install it with: `pip install agent-cli[vad]` or `uv sync --extra vad`."
    )
    raise ImportError(msg) from e

LOGGER = logging.getLogger(__name__)

# Silero VAD model URL and cache location
SILERO_VAD_URL = (
    "https://github.com/snakers4/silero-vad/raw/v5.1.2/src/silero_vad/data/silero_vad.onnx"
)
SILERO_VAD_CACHE = Path.home() / ".cache" / "agent-cli" / "silero_vad.onnx"


def _get_model_path() -> Path:
    """Get path to Silero VAD ONNX model, downloading if needed."""
    if SILERO_VAD_CACHE.exists():
        return SILERO_VAD_CACHE

    LOGGER.info("Downloading Silero VAD model...")
    SILERO_VAD_CACHE.parent.mkdir(parents=True, exist_ok=True)

    # Download with progress
    urllib.request.urlretrieve(SILERO_VAD_URL, SILERO_VAD_CACHE)  # noqa: S310
    LOGGER.info("Silero VAD model downloaded to %s", SILERO_VAD_CACHE)
    return SILERO_VAD_CACHE


class _SileroVADOnnx:
    """Pure numpy wrapper for Silero VAD ONNX model."""

    def __init__(self, *, force_cpu: bool = True) -> None:
        """Initialize the ONNX model session."""
        model_path = _get_model_path()

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1

        providers = ["CPUExecutionProvider"] if force_cpu else None
        self._session = onnxruntime.InferenceSession(
            str(model_path),
            providers=providers,
            sess_options=opts,
        )
        self._sample_rates = [8000, 16000]
        self.reset_states()

    def reset_states(self, batch_size: int = 1) -> None:
        """Reset the internal state for a new audio stream."""
        self._state = np.zeros((2, batch_size, 128), dtype=np.float32)
        self._context = np.zeros(0, dtype=np.float32)
        self._last_sr = 0
        self._last_batch_size = 0

    def __call__(self, audio: np.ndarray, sample_rate: int) -> float:
        """Process an audio chunk and return speech probability.

        Args:
            audio: Audio samples as float32 numpy array (512 samples for 16kHz, 256 for 8kHz)
            sample_rate: Sample rate (8000 or 16000)

        Returns:
            Speech probability (0.0 to 1.0)

        """
        if sample_rate not in self._sample_rates:
            msg = f"Supported sample rates: {self._sample_rates}"
            raise ValueError(msg)

        # Expected samples per chunk
        num_samples = 512 if sample_rate == 16000 else 256  # noqa: PLR2004
        context_size = 64 if sample_rate == 16000 else 32  # noqa: PLR2004

        if len(audio) != num_samples:
            msg = f"Expected {num_samples} samples for {sample_rate}Hz, got {len(audio)}"
            raise ValueError(msg)

        # Ensure 2D: [batch, samples]
        if audio.ndim == 1:
            audio = audio.reshape(1, -1)

        batch_size = audio.shape[0]

        # Reset state if sample rate or batch size changed
        if self._last_sr and self._last_sr != sample_rate:
            self.reset_states(batch_size)
        if self._last_batch_size and self._last_batch_size != batch_size:
            self.reset_states(batch_size)
        if not self._last_batch_size:
            self.reset_states(batch_size)

        # Initialize context if empty
        if len(self._context) == 0:
            self._context = np.zeros((batch_size, context_size), dtype=np.float32)

        # Concatenate context with audio
        x = np.concatenate([self._context, audio], axis=1)

        # Run ONNX inference
        ort_inputs = {
            "input": x,
            "state": self._state,
            "sr": np.array(sample_rate, dtype=np.int64),
        }
        out, self._state = self._session.run(None, ort_inputs)

        # Update context with last samples
        self._context = x[:, -context_size:]
        self._last_sr = sample_rate
        self._last_batch_size = batch_size

        return float(out[0, 0])


class VoiceActivityDetector:
    """Silero VAD-based voice activity detection for audio segmentation.

    Processes audio chunks and emits complete speech segments when silence
    is detected after speech.
    """

    def __init__(
        self,
        sample_rate: int = constants.AUDIO_RATE,
        threshold: float = 0.3,
        silence_threshold_ms: int = 1000,
        min_speech_duration_ms: int = 250,
        pre_speech_buffer_ms: int = 300,
    ) -> None:
        """Initialize VAD with configurable thresholds."""
        if sample_rate not in (8000, 16000):
            msg = f"Sample rate must be 8000 or 16000, got {sample_rate}"
            raise ValueError(msg)

        self.sample_rate = sample_rate
        self.threshold = threshold
        self.silence_threshold_ms = silence_threshold_ms
        self.min_speech_duration_ms = min_speech_duration_ms

        # Window size: 512 samples @ 16kHz, 256 @ 8kHz (Silero requirement)
        self.window_size_samples = 512 if sample_rate == 16000 else 256  # noqa: PLR2004
        self.window_size_bytes = self.window_size_samples * 2  # 16-bit audio

        # Pre-speech buffer size in windows
        pre_speech_windows = max(
            1,
            (pre_speech_buffer_ms * sample_rate // 1000) // self.window_size_samples,
        )

        # Model and state
        self._model = _SileroVADOnnx()
        self._pre_speech_buffer: deque[bytes] = deque(maxlen=pre_speech_windows)
        self._pending = bytearray()
        self._audio_buffer = bytearray()
        self._is_speaking = False
        self._silence_samples = 0
        self._speech_samples = 0

    @property
    def _silence_threshold_samples(self) -> int:
        return self.silence_threshold_ms * self.sample_rate // 1000

    @property
    def _min_speech_samples(self) -> int:
        return self.min_speech_duration_ms * self.sample_rate // 1000

    def reset(self) -> None:
        """Reset VAD state for a new recording session."""
        self._model.reset_states()
        self._pre_speech_buffer.clear()
        self._pending.clear()
        self._audio_buffer.clear()
        self._is_speaking = False
        self._silence_samples = 0
        self._speech_samples = 0

    def _is_speech(self, window: bytes) -> bool:
        """Check if audio window contains speech."""
        audio = np.frombuffer(window, dtype=np.int16).astype(np.float32) / 32768.0
        prob = self._model(audio, self.sample_rate)
        LOGGER.debug("Speech prob: %.3f, threshold: %.2f", prob, self.threshold)
        return prob >= self.threshold

    def process_chunk(self, chunk: bytes) -> tuple[bool, bytes | None]:
        """Process audio chunk and detect speech segments.

        Returns (is_speaking, completed_segment_or_none).
        """
        self._pending.extend(chunk)
        completed_segment: bytes | None = None
        ws = self.window_size_bytes

        # Process complete windows
        while len(self._pending) >= ws:
            window = bytes(self._pending[:ws])
            del self._pending[:ws]

            if self._is_speech(window):
                if not self._is_speaking:
                    # Speech just started - prepend pre-speech buffer
                    self._is_speaking = True
                    self._audio_buffer.clear()
                    for pre in self._pre_speech_buffer:
                        self._audio_buffer.extend(pre)
                    self._pre_speech_buffer.clear()
                    self._silence_samples = 0
                    self._speech_samples = 0

                self._audio_buffer.extend(window)
                self._silence_samples = 0
                self._speech_samples += self.window_size_samples

            elif self._is_speaking:
                # Silence during speech
                self._audio_buffer.extend(window)
                self._silence_samples += self.window_size_samples

                if self._silence_samples >= self._silence_threshold_samples:
                    # Segment complete - trim trailing silence
                    if self._speech_samples >= self._min_speech_samples:
                        trailing = (self._silence_samples // self.window_size_samples) * ws
                        completed_segment = bytes(
                            self._audio_buffer[:-trailing] if trailing else self._audio_buffer,
                        )

                    # Reset for next segment
                    self._is_speaking = False
                    self._silence_samples = 0
                    self._speech_samples = 0
                    self._audio_buffer.clear()
                    self._model.reset_states()
            else:
                # Not speaking - maintain rolling pre-speech buffer (auto-limited by deque maxlen)
                self._pre_speech_buffer.append(window)

        return self._is_speaking, completed_segment

    def flush(self) -> bytes | None:
        """Flush any remaining buffered speech when stream ends."""
        if self._is_speaking and self._speech_samples >= self._min_speech_samples:
            result = bytes(self._audio_buffer)
            self.reset()
            return result
        self.reset()
        return None

    def get_segment_duration_seconds(self, segment: bytes) -> float:
        """Calculate duration of audio segment in seconds."""
        return len(segment) // 2 / self.sample_rate
