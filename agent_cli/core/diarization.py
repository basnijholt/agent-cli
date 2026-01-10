"""Speaker diarization using pyannote-audio."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyannote.core import Annotation


def _check_pyannote_installed() -> None:
    """Check if pyannote-audio is installed, raise ImportError with helpful message if not."""
    try:
        import pyannote.audio  # noqa: F401, PLC0415
    except ImportError as e:
        msg = (
            "pyannote-audio is required for speaker diarization. "
            "Install it with: `pip install agent-cli[diarization]` or `uv sync --extra diarization`."
        )
        raise ImportError(msg) from e


@dataclass
class DiarizedSegment:
    """A segment of speech attributed to a specific speaker."""

    speaker: str
    start: float
    end: float
    text: str = ""


class SpeakerDiarizer:
    """Wrapper for pyannote speaker diarization pipeline.

    Requires a HuggingFace token with access to pyannote/speaker-diarization-3.1.
    Users must accept the license at: https://huggingface.co/pyannote/speaker-diarization-3.1
    """

    def __init__(
        self,
        hf_token: str,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> None:
        """Initialize the diarization pipeline.

        Args:
            hf_token: HuggingFace token for accessing pyannote models.
            min_speakers: Minimum number of speakers (optional hint).
            max_speakers: Maximum number of speakers (optional hint).

        """
        _check_pyannote_installed()
        from pyannote.audio import Pipeline  # noqa: PLC0415

        self.pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token,
        )
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers

    def diarize(self, audio_path: Path) -> list[DiarizedSegment]:
        """Run diarization on audio file, return speaker segments.

        Args:
            audio_path: Path to the audio file (WAV format recommended).

        Returns:
            List of DiarizedSegment with speaker labels and timestamps.

        """
        import torchaudio  # noqa: PLC0415

        # Build kwargs for speaker count hints
        kwargs: dict[str, int] = {}
        if self.min_speakers is not None:
            kwargs["min_speakers"] = self.min_speakers
        if self.max_speakers is not None:
            kwargs["max_speakers"] = self.max_speakers

        # Pre-load audio to avoid torchcodec/FFmpeg issues
        waveform, sample_rate = torchaudio.load(str(audio_path))
        audio_input = {"waveform": waveform, "sample_rate": sample_rate}

        # Run the pipeline
        output = self.pipeline(audio_input, **kwargs)

        # Handle both old (Annotation) and new (DiarizeOutput) API
        if hasattr(output, "speaker_diarization"):
            # New API: DiarizeOutput dataclass
            diarization: Annotation = output.speaker_diarization
        else:
            # Old API: returns Annotation directly
            diarization = output

        # Convert to our dataclass format
        segments: list[DiarizedSegment] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                DiarizedSegment(
                    speaker=speaker,
                    start=turn.start,
                    end=turn.end,
                ),
            )

        return segments


def align_transcript_with_speakers(
    transcript: str,
    segments: list[DiarizedSegment],
) -> list[DiarizedSegment]:
    """Align transcript text with speaker segments using simple word distribution.

    This is a basic alignment that distributes words proportionally based on
    segment duration. For more accurate word-level alignment, consider using
    WhisperX or similar tools.

    Args:
        transcript: The full transcript text.
        segments: List of speaker segments with timestamps.

    Returns:
        List of DiarizedSegment with text filled in.

    """
    if not segments:
        return segments

    words = transcript.split()
    if not words:
        return segments

    # Calculate total duration
    total_duration = sum(seg.end - seg.start for seg in segments)
    if total_duration <= 0:
        # Fallback: distribute words evenly
        words_per_segment = len(words) // len(segments)
        result = []
        word_idx = 0
        for i, seg in enumerate(segments):
            # Last segment gets remaining words
            if i == len(segments) - 1:
                seg_words = words[word_idx:]
            else:
                seg_words = words[word_idx : word_idx + words_per_segment]
                word_idx += words_per_segment
            result.append(
                DiarizedSegment(
                    speaker=seg.speaker,
                    start=seg.start,
                    end=seg.end,
                    text=" ".join(seg_words),
                ),
            )
        return result

    # Distribute words based on segment duration
    result = []
    word_idx = 0
    for i, seg in enumerate(segments):
        seg_duration = seg.end - seg.start
        # Calculate proportion of words for this segment
        if i == len(segments) - 1:
            # Last segment gets all remaining words
            seg_words = words[word_idx:]
        else:
            proportion = seg_duration / total_duration
            word_count = max(1, round(proportion * len(words)))
            seg_words = words[word_idx : word_idx + word_count]
            word_idx += word_count
            # Adjust total_duration for remaining segments
            total_duration -= seg_duration

        result.append(
            DiarizedSegment(
                speaker=seg.speaker,
                start=seg.start,
                end=seg.end,
                text=" ".join(seg_words),
            ),
        )

    return result


def format_diarized_output(
    segments: list[DiarizedSegment],
    output_format: str = "inline",
) -> str:
    """Format diarized segments for output.

    Args:
        segments: List of DiarizedSegment with speaker labels and text.
        output_format: "inline" for human-readable, "json" for structured output.

    Returns:
        Formatted string representation of the diarized transcript.

    """
    if output_format == "json":
        data = {
            "segments": [
                {
                    "speaker": seg.speaker,
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text,
                }
                for seg in segments
            ],
        }
        return json.dumps(data, indent=2)

    # Inline format: [Speaker X]: text
    lines = [f"[{seg.speaker}]: {seg.text}" for seg in segments if seg.text]
    return "\n".join(lines)
