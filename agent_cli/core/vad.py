"""Voice Activity Detection using webrtcvad for speech segmentation."""

from __future__ import annotations

import io
from dataclasses import dataclass, field

try:
    import webrtcvad
except ImportError as e:
    msg = (
        "webrtcvad is required for the transcribe-daemon command. "
        "Install it with: pip install 'agent-cli[vad]'"
    )
    raise ImportError(msg) from e

from agent_cli import constants


@dataclass
class VoiceActivityDetector:
    """webrtcvad-based voice activity detection for audio segmentation.

    This class processes audio chunks and detects speech segments by tracking
    voice activity and silence periods. When a silence threshold is exceeded
    after speech, it emits the complete speech segment.

    Args:
        aggressiveness: VAD aggressiveness mode (0-3). Higher values are more
            aggressive at filtering out non-speech. Default is 2.
        sample_rate: Audio sample rate in Hz. Must be 8000, 16000, 32000, or 48000.
        frame_duration_ms: Duration of each VAD frame in milliseconds.
            Must be 10, 20, or 30. Default is 30.
        silence_threshold_ms: Duration of silence (in ms) required to end a segment.
        min_speech_duration_ms: Minimum speech duration (in ms) to trigger a segment.

    """

    aggressiveness: int = 2
    sample_rate: int = constants.AUDIO_RATE
    frame_duration_ms: int = 30
    silence_threshold_ms: int = 1000
    min_speech_duration_ms: int = 500

    # Internal state
    _vad: webrtcvad.Vad = field(init=False, repr=False)
    _audio_buffer: io.BytesIO = field(init=False, repr=False)
    _is_speaking: bool = field(init=False, default=False)
    _silence_frames: int = field(init=False, default=0)
    _speech_frames: int = field(init=False, default=0)
    _pending_chunks: list[bytes] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the VAD instance and internal buffers."""
        if self.aggressiveness < 0 or self.aggressiveness > 3:  # noqa: PLR2004
            msg = f"Aggressiveness must be 0-3, got {self.aggressiveness}"
            raise ValueError(msg)

        if self.sample_rate not in (8000, 16000, 32000, 48000):
            msg = f"Sample rate must be 8000, 16000, 32000, or 48000, got {self.sample_rate}"
            raise ValueError(msg)

        if self.frame_duration_ms not in (10, 20, 30):
            msg = f"Frame duration must be 10, 20, or 30ms, got {self.frame_duration_ms}"
            raise ValueError(msg)

        self._vad = webrtcvad.Vad(self.aggressiveness)
        self._audio_buffer = io.BytesIO()
        self._pending_chunks = []
        self._is_speaking = False
        self._silence_frames = 0
        self._speech_frames = 0

    @property
    def frame_size_bytes(self) -> int:
        """Calculate the frame size in bytes for VAD processing."""
        # 16-bit audio = 2 bytes per sample
        samples_per_frame = self.sample_rate * self.frame_duration_ms // 1000
        return samples_per_frame * 2  # 2 bytes per sample (int16)

    @property
    def _silence_threshold_frames(self) -> int:
        """Number of silence frames needed to end a segment."""
        return self.silence_threshold_ms // self.frame_duration_ms

    @property
    def _min_speech_frames(self) -> int:
        """Minimum number of speech frames for a valid segment."""
        return self.min_speech_duration_ms // self.frame_duration_ms

    def reset(self) -> None:
        """Reset the VAD state for a new recording session."""
        self._audio_buffer = io.BytesIO()
        self._pending_chunks = []
        self._is_speaking = False
        self._silence_frames = 0
        self._speech_frames = 0

    def process_chunk(self, audio_chunk: bytes) -> tuple[bool, bytes | None]:
        """Process an audio chunk and detect speech segments.

        This method buffers incoming audio and processes it frame-by-frame
        using webrtcvad. When speech ends (silence threshold exceeded), it
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
        frame_size = self.frame_size_bytes

        # Process complete frames
        offset = 0
        while offset + frame_size <= len(pending_data):
            frame = pending_data[offset : offset + frame_size]
            offset += frame_size

            try:
                is_speech = self._vad.is_speech(frame, self.sample_rate)
            except Exception:
                # If VAD fails, assume no speech
                is_speech = False

            if is_speech:
                self._silence_frames = 0
                self._speech_frames += 1

                if not self._is_speaking:
                    # Start of speech detected
                    self._is_speaking = True
                    self._audio_buffer = io.BytesIO()

                # Buffer the speech frame
                self._audio_buffer.write(frame)

            elif self._is_speaking:
                # We were speaking, now silence
                self._silence_frames += 1
                # Still buffer during short silences
                self._audio_buffer.write(frame)

                # Check if silence threshold exceeded
                if self._silence_frames >= self._silence_threshold_frames:
                    # Check minimum speech duration
                    if self._speech_frames >= self._min_speech_frames:
                        # Emit the segment (trim trailing silence)
                        segment_data = self._audio_buffer.getvalue()
                        # Remove trailing silence frames
                        trailing_bytes = self._silence_frames * frame_size
                        if trailing_bytes < len(segment_data):
                            segment_data = segment_data[:-trailing_bytes]
                        completed_segment = segment_data

                    # Reset state for next segment
                    self._is_speaking = False
                    self._silence_frames = 0
                    self._speech_frames = 0
                    self._audio_buffer = io.BytesIO()

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
        if self._is_speaking and self._speech_frames >= self._min_speech_frames:
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
