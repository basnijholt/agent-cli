"""Speaker diarization using pyannote-audio."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

from agent_cli.core.alignment import AlignedWord, align

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


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving punctuation."""
    # Split on sentence-ending punctuation followed by space or end
    pattern = r"(?<=[.!?])\s+"
    sentences = re.split(pattern, text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _get_dominant_speaker(
    start_time: float,
    end_time: float,
    segments: list[DiarizedSegment],
) -> str | None:
    """Find which speaker is dominant during a time range."""
    speaker_durations: dict[str, float] = {}

    for seg in segments:
        # Calculate overlap between time range and segment
        overlap_start = max(start_time, seg.start)
        overlap_end = min(end_time, seg.end)
        overlap = max(0, overlap_end - overlap_start)

        if overlap > 0:
            speaker_durations[seg.speaker] = speaker_durations.get(seg.speaker, 0) + overlap

    if not speaker_durations:
        return None

    return max(speaker_durations, key=lambda s: speaker_durations[s])


def align_transcript_with_speakers(
    transcript: str,
    segments: list[DiarizedSegment],
) -> list[DiarizedSegment]:
    """Align transcript sentences with speaker segments.

    Uses sentence-based alignment to avoid splitting sentences mid-phrase.
    Each sentence is assigned to the speaker who is dominant during
    its estimated time range.

    Args:
        transcript: The full transcript text.
        segments: List of speaker segments with timestamps.

    Returns:
        List of DiarizedSegment with text, one per sentence, merged by speaker.

    """
    if not segments or not transcript.strip():
        return segments

    sentences = _split_into_sentences(transcript)
    if not sentences:
        return segments

    # Calculate total duration and timing
    audio_start = min(seg.start for seg in segments)
    audio_end = max(seg.end for seg in segments)
    total_duration = audio_end - audio_start

    if total_duration <= 0:
        # Fallback: assign all text to first speaker
        return [
            DiarizedSegment(
                speaker=segments[0].speaker,
                start=segments[0].start,
                end=segments[-1].end,
                text=transcript,
            ),
        ]

    # Count total characters to estimate timing
    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        return segments

    # Assign each sentence to a speaker based on estimated timing
    result: list[DiarizedSegment] = []
    current_time = audio_start

    for sentence in sentences:
        # Estimate sentence duration based on character proportion
        sentence_duration = (len(sentence) / total_chars) * total_duration
        sentence_end = current_time + sentence_duration

        # Find dominant speaker for this time range
        speaker = _get_dominant_speaker(current_time, sentence_end, segments)
        if speaker is None:
            # No speaker found, use the last known speaker or first
            speaker = result[-1].speaker if result else segments[0].speaker

        # Merge with previous segment if same speaker
        if result and result[-1].speaker == speaker:
            result[-1] = DiarizedSegment(
                speaker=speaker,
                start=result[-1].start,
                end=sentence_end,
                text=result[-1].text + " " + sentence,
            )
        else:
            result.append(
                DiarizedSegment(
                    speaker=speaker,
                    start=current_time,
                    end=sentence_end,
                    text=sentence,
                ),
            )

        current_time = sentence_end

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


def align_words_to_speakers(
    words: list[AlignedWord],
    segments: list[DiarizedSegment],
) -> list[DiarizedSegment]:
    """Assign speakers to words using precise word timestamps.

    Args:
        words: List of AlignedWord with start/end times from forced alignment.
        segments: List of speaker segments from diarization.

    Returns:
        List of DiarizedSegment with text, merged by consecutive speaker.

    """
    if not segments or not words:
        return segments

    result: list[DiarizedSegment] = []

    for word in words:
        # Find speaker with most overlap for this word
        speaker = _get_dominant_speaker(word.start, word.end, segments)
        if speaker is None:
            # Use last known speaker or first segment's speaker
            speaker = result[-1].speaker if result else segments[0].speaker

        # Merge with previous segment if same speaker
        if result and result[-1].speaker == speaker:
            result[-1] = DiarizedSegment(
                speaker=speaker,
                start=result[-1].start,
                end=word.end,
                text=result[-1].text + " " + word.word,
            )
        else:
            result.append(
                DiarizedSegment(
                    speaker=speaker,
                    start=word.start,
                    end=word.end,
                    text=word.word,
                ),
            )

    return result


def align_transcript_with_words(
    transcript: str,
    segments: list[DiarizedSegment],
    audio_path: Path,
    language: str = "en",
) -> list[DiarizedSegment]:
    """Align transcript using wav2vec2 forced alignment for word-level precision.

    Args:
        transcript: The full transcript text.
        segments: List of speaker segments from diarization.
        audio_path: Path to the audio file for alignment.
        language: Language code for alignment model.

    Returns:
        List of DiarizedSegment with precise word-level speaker assignment.

    """
    if not segments or not transcript.strip():
        return segments

    words = align(audio_path, transcript, language)
    return align_words_to_speakers(words, segments)
