"""Speaker diarization using pyannote-audio."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

from agent_cli import constants
from agent_cli.core.alignment import AlignedWord, align
from agent_cli.core.audio_format import convert_audio_to_wyoming_format

if TYPE_CHECKING:
    import torch
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


def _load_audio_for_diarization(audio_path: Path) -> tuple[torch.Tensor, int]:
    """Load audio for diarization, falling back to FFmpeg conversion when needed."""
    import torch  # noqa: PLC0415
    import torchaudio  # noqa: PLC0415

    def normalize_waveform(
        waveform: torch.Tensor,
        sample_rate: int,
    ) -> tuple[torch.Tensor, int]:
        if waveform.dim() > 1 and waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)
        if sample_rate != constants.AUDIO_RATE:
            waveform = torchaudio.functional.resample(
                waveform,
                sample_rate,
                constants.AUDIO_RATE,
            )
            sample_rate = constants.AUDIO_RATE
        if waveform.dtype != torch.float32:
            waveform = waveform.float()
        return waveform, sample_rate

    if audio_path.suffix.lower() == ".wav":
        try:
            waveform, sample_rate = torchaudio.load(str(audio_path))
        except (RuntimeError, OSError, ValueError):
            waveform = None
        else:
            return normalize_waveform(waveform, sample_rate)

    pcm_data = convert_audio_to_wyoming_format(audio_path.read_bytes(), audio_path.name)
    try:
        pcm_tensor = torch.frombuffer(pcm_data, dtype=torch.int16)
    except (AttributeError, TypeError):
        import numpy as np  # noqa: PLC0415

        pcm_tensor = torch.from_numpy(np.frombuffer(pcm_data, dtype=np.int16))
    waveform = pcm_tensor.float().div(32768.0).unsqueeze(0)
    return normalize_waveform(waveform, constants.AUDIO_RATE)


@dataclass
class DiarizedSegment:
    """A segment of speech attributed to a specific speaker."""

    speaker: str
    start: float
    end: float
    text: str = ""


_ABBREVIATIONS = {
    "dr.",
    "mr.",
    "mrs.",
    "ms.",
    "prof.",
    "sr.",
    "jr.",
    "st.",
    "vs.",
    "etc.",
    "e.g.",
    "i.e.",
    "u.s.",
    "u.k.",
    "a.m.",
    "p.m.",
    "no.",
}
_INITIALISM_RE = re.compile(r"(?:[A-Za-z]\.){2,}$")
_SINGLE_INITIAL_LEN = 2


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
        # Build kwargs for speaker count hints
        kwargs: dict[str, int] = {}
        if self.min_speakers is not None:
            kwargs["min_speakers"] = self.min_speakers
        if self.max_speakers is not None:
            kwargs["max_speakers"] = self.max_speakers

        # Pre-load audio to avoid torchcodec/FFmpeg issues
        waveform, sample_rate = _load_audio_for_diarization(audio_path)
        audio_input = {"waveform": waveform, "sample_rate": sample_rate}

        # Run the pipeline
        output = self.pipeline(audio_input, **kwargs)
        diarization: Annotation = output.speaker_diarization

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
        segments.sort(key=lambda segment: (segment.start, segment.end))

        return segments


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving punctuation."""
    text = text.strip()
    if not text:
        return []

    def is_abbreviation(token: str) -> bool:
        token = token.strip("\"')]}").lower()
        if token in _ABBREVIATIONS:
            return True
        if _INITIALISM_RE.match(token):
            return True
        return len(token) == _SINGLE_INITIAL_LEN and token[0].isalpha() and token[1] == "."

    sentences: list[str] = []
    start = 0
    pattern = re.compile(r"[.!?](?:[\"'\)\]\}]+)?")

    for match in pattern.finditer(text):
        end = match.end()
        if end < len(text) and not text[end].isspace():
            continue
        chunk = text[start:end].strip()
        if not chunk:
            start = end
            continue
        last_token = chunk.split()[-1]
        if is_abbreviation(last_token):
            continue
        sentences.append(chunk)
        start = end

    remainder = text[start:].strip()
    if remainder:
        sentences.append(remainder)

    return sentences


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
    sorted_segments = sorted(segments, key=lambda seg: (seg.start, seg.end))
    current_time = audio_start
    start_index = 0

    for sentence in sentences:
        # Estimate sentence duration based on character proportion
        sentence_duration = (len(sentence) / total_chars) * total_duration
        sentence_end = current_time + sentence_duration

        # Find dominant speaker for this time range
        speaker, start_index = _get_dominant_speaker_window(
            current_time,
            sentence_end,
            sorted_segments,
            start_index,
        )
        if speaker is None:
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


def _get_dominant_speaker_window(
    start_time: float,
    end_time: float,
    segments: list[DiarizedSegment],
    start_index: int,
) -> tuple[str | None, int]:
    """Find dominant speaker within a time window using an index cursor."""
    speaker_durations: dict[str, float] = {}
    idx = start_index

    while idx < len(segments) and segments[idx].end <= start_time:
        idx += 1

    scan = idx
    while scan < len(segments) and segments[scan].start < end_time:
        seg = segments[scan]
        overlap_start = max(start_time, seg.start)
        overlap_end = min(end_time, seg.end)
        overlap = max(0, overlap_end - overlap_start)
        if overlap > 0:
            speaker_durations[seg.speaker] = speaker_durations.get(seg.speaker, 0) + overlap
        scan += 1

    if not speaker_durations:
        return None, idx

    speaker = max(speaker_durations, key=lambda s: speaker_durations[s])
    return speaker, idx


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
    sorted_segments = sorted(segments, key=lambda segment: (segment.start, segment.end))
    start_index = 0

    for word in words:
        # Find speaker with most overlap for this word
        speaker, start_index = _get_dominant_speaker_window(
            word.start,
            word.end,
            sorted_segments,
            start_index,
        )
        if speaker is None:
            # Use last known speaker or first segment's speaker
            speaker = result[-1].speaker if result else sorted_segments[0].speaker

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
    if not words:
        return align_transcript_with_speakers(transcript, segments)
    return align_words_to_speakers(words, segments)
