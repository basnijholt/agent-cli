"""Voice Activity Detection using Silero VAD for speech segmentation."""

from __future__ import annotations

import logging
from collections import deque

from agent_cli import constants

try:
    import numpy as np
    from silero_vad_lite import SileroVAD
except ImportError as e:
    msg = (
        "silero-vad-lite is required for the transcribe-daemon command. "
        "Install it with: `pip install agent-cli[vad]` or `uv sync --extra vad`."
    )
    raise ImportError(msg) from e

LOGGER = logging.getLogger(__name__)


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
        self._model = SileroVAD(sample_rate=sample_rate)
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
        self._model = SileroVAD(sample_rate=self.sample_rate)
        self._pre_speech_buffer.clear()
        self._pending.clear()
        self._audio_buffer.clear()
        self._is_speaking = False
        self._silence_samples = 0
        self._speech_samples = 0

    def _is_speech(self, window: bytes) -> bool:
        """Check if audio window contains speech."""
        audio = np.frombuffer(window, dtype=np.int16).astype(np.float32) / 32768.0
        prob = self._model.process(audio)
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
                    self._model = SileroVAD(sample_rate=self.sample_rate)
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
