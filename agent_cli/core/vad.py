"""Voice Activity Detection using Silero VAD for speech segmentation."""

from __future__ import annotations

import io
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import numpy as np
    from silero_vad.utils_vad import OnnxWrapper, VADIterator
except ImportError as e:
    msg = (
        "silero-vad is required for the transcribe-daemon command. "
        "Install it with: pip install 'agent-cli[vad]'"
    )
    raise ImportError(msg) from e

from agent_cli import constants

# URL for the Silero VAD ONNX model
_SILERO_VAD_ONNX_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
)


def _get_silero_model_path() -> Path:
    """Get the path to the Silero VAD ONNX model, downloading if needed."""
    cache_dir = Path.home() / ".cache" / "silero-vad"
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_path = cache_dir / "silero_vad.onnx"

    if not model_path.exists():
        # Download the model
        urllib.request.urlretrieve(_SILERO_VAD_ONNX_URL, model_path)  # noqa: S310

    return model_path


@dataclass
class VoiceActivityDetector:
    """Silero VAD-based voice activity detection for audio segmentation.

    This class processes audio chunks and detects speech segments by tracking
    voice activity and silence periods. When a silence threshold is exceeded
    after speech, it emits the complete speech segment.

    Args:
        sample_rate: Audio sample rate in Hz. Must be 8000 or 16000.
        silence_threshold_ms: Duration of silence (in ms) required to end a segment.
        min_speech_duration_ms: Minimum speech duration (in ms) to trigger a segment.
        threshold: Speech detection threshold (0.0-1.0). Higher = more aggressive.

    """

    sample_rate: int = constants.AUDIO_RATE
    silence_threshold_ms: int = 1000
    min_speech_duration_ms: int = 500
    threshold: float = 0.5

    # Internal state
    _model: Any = field(init=False, repr=False)
    _vad_iterator: VADIterator = field(init=False, repr=False)
    _audio_buffer: io.BytesIO = field(init=False, repr=False)
    _is_speaking: bool = field(init=False, default=False)
    _silence_samples: int = field(init=False, default=0)
    _speech_samples: int = field(init=False, default=0)
    _pending_chunks: list[bytes] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the VAD model and internal buffers."""
        if self.sample_rate not in (8000, 16000):
            msg = f"Sample rate must be 8000 or 16000, got {self.sample_rate}"
            raise ValueError(msg)

        # Load Silero VAD ONNX model
        model_path = _get_silero_model_path()
        self._model = OnnxWrapper(str(model_path))
        self._vad_iterator = VADIterator(
            self._model,
            sampling_rate=self.sample_rate,
            threshold=self.threshold,
            # Match Silero's silence detection to our threshold to prevent flickering
            min_silence_duration_ms=self.silence_threshold_ms,
        )
        self._audio_buffer = io.BytesIO()
        self._pending_chunks = []
        self._is_speaking = False
        self._silence_samples = 0
        self._speech_samples = 0

    @property
    def window_size_samples(self) -> int:
        """Get the window size in samples for VAD processing."""
        # Silero VAD uses 512 samples for 16kHz, 256 for 8kHz
        return 512 if self.sample_rate == 16000 else 256  # noqa: PLR2004

    @property
    def window_size_bytes(self) -> int:
        """Get the window size in bytes for VAD processing."""
        # 16-bit audio = 2 bytes per sample
        return self.window_size_samples * 2

    @property
    def _silence_threshold_samples(self) -> int:
        """Number of silence samples needed to end a segment."""
        return self.silence_threshold_ms * self.sample_rate // 1000

    @property
    def _min_speech_samples(self) -> int:
        """Minimum number of speech samples for a valid segment."""
        return self.min_speech_duration_ms * self.sample_rate // 1000

    def reset(self) -> None:
        """Reset the VAD state for a new recording session."""
        self._vad_iterator.reset_states()
        self._audio_buffer = io.BytesIO()
        self._pending_chunks = []
        self._is_speaking = False
        self._silence_samples = 0
        self._speech_samples = 0

    def _bytes_to_array(self, audio_bytes: bytes) -> np.ndarray:
        """Convert raw PCM bytes to a numpy array."""
        # Convert bytes to int16 numpy array
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
        # Convert to float32 and normalize to [-1, 1]
        return audio_np.astype(np.float32) / 32768.0

    def process_chunk(self, audio_chunk: bytes) -> tuple[bool, bytes | None]:
        """Process an audio chunk and detect speech segments.

        This method buffers incoming audio and processes it window-by-window
        using Silero VAD. When speech ends (silence threshold exceeded), it
        returns the complete speech segment.

        Args:
            audio_chunk: Raw PCM audio data (16-bit, mono).

        Returns:
            A tuple of (is_speech, completed_segment).
            - is_speech: True if currently detecting speech
            - completed_segment: The audio bytes of a completed segment, or None

        """
        # Add chunk to pending buffer
        self._pending_chunks.append(audio_chunk)
        pending_data = b"".join(self._pending_chunks)

        completed_segment: bytes | None = None
        window_size = self.window_size_bytes

        # Process complete windows
        offset = 0
        while offset + window_size <= len(pending_data):
            window = pending_data[offset : offset + window_size]
            offset += window_size

            # Convert to numpy array and run VAD
            audio_array = self._bytes_to_array(window)
            speech_dict = self._vad_iterator(audio_array, return_seconds=False)

            # Use the VADIterator's triggered state to determine if speech is active
            # This is more reliable than just checking start/end events
            is_speech = self._vad_iterator.triggered

            # Check for speech start event to initialize our buffers
            if speech_dict and "start" in speech_dict and not self._is_speaking:
                self._is_speaking = True
                self._audio_buffer = io.BytesIO()
                self._silence_samples = 0
                self._speech_samples = 0

            if self._is_speaking:
                self._audio_buffer.write(window)

                if is_speech:
                    self._silence_samples = 0
                    self._speech_samples += self.window_size_samples
                else:
                    self._silence_samples += self.window_size_samples

                # Check if silence threshold exceeded
                if self._silence_samples >= self._silence_threshold_samples:
                    # Check minimum speech duration
                    if self._speech_samples >= self._min_speech_samples:
                        # Emit the segment (trim trailing silence)
                        segment_data = self._audio_buffer.getvalue()
                        trailing_bytes = (
                            self._silence_samples // self.window_size_samples
                        ) * window_size
                        if trailing_bytes < len(segment_data):
                            segment_data = segment_data[:-trailing_bytes]
                        completed_segment = segment_data

                    # Reset state for next segment
                    self._is_speaking = False
                    self._silence_samples = 0
                    self._speech_samples = 0
                    self._audio_buffer = io.BytesIO()
                    self._vad_iterator.reset_states()

        # Keep remaining incomplete data for next call
        remaining = pending_data[offset:]
        self._pending_chunks = [remaining] if remaining else []

        return self._is_speaking, completed_segment

    def flush(self) -> bytes | None:
        """Flush any remaining buffered speech.

        Call this when the audio stream ends to get any remaining speech
        that hasn't been emitted yet.

        Returns:
            The remaining audio bytes if there was speech, or None.

        """
        if self._is_speaking and self._speech_samples >= self._min_speech_samples:
            segment_data = self._audio_buffer.getvalue()
            self.reset()
            return segment_data
        self.reset()
        return None

    def get_segment_duration_seconds(self, segment: bytes) -> float:
        """Calculate the duration of an audio segment in seconds.

        Args:
            segment: Raw PCM audio data.

        Returns:
            Duration in seconds.

        """
        # 2 bytes per sample (int16), mono
        num_samples = len(segment) // 2
        return num_samples / self.sample_rate
