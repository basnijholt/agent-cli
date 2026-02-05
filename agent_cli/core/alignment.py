"""Forced alignment using wav2vec2 for word-level timestamps.

Based on whisperx's alignment approach.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import torch

SAMPLE_RATE = 16000

# Torchaudio bundled models
ALIGN_MODELS: dict[str, str] = {
    "en": "WAV2VEC2_ASR_BASE_960H",
    "fr": "VOXPOPULI_ASR_BASE_10K_FR",
    "de": "VOXPOPULI_ASR_BASE_10K_DE",
    "es": "VOXPOPULI_ASR_BASE_10K_ES",
    "it": "VOXPOPULI_ASR_BASE_10K_IT",
}


@dataclass
class AlignedWord:
    """A word with start/end timestamps."""

    word: str
    start: float
    end: float


def align(
    audio_path: Path,
    transcript: str,
    language: str = "en",
    device: str = "cpu",
) -> list[AlignedWord]:
    """Align transcript to audio, returning word-level timestamps.

    Args:
        audio_path: Path to audio file.
        transcript: Text to align.
        language: Language code (en, fr, de, es, it).
        device: Device to run on (cpu or cuda).

    Returns:
        List of words with timestamps.

    """
    import torch  # noqa: PLC0415
    import torchaudio  # noqa: PLC0415

    if language not in ALIGN_MODELS:
        msg = f"No alignment model for language: {language}. Supported: {list(ALIGN_MODELS.keys())}"
        raise ValueError(msg)

    # Load model
    bundle = torchaudio.pipelines.__dict__[ALIGN_MODELS[language]]
    model = bundle.get_model().to(device)
    labels = bundle.get_labels()
    dictionary = {c.lower(): i for i, c in enumerate(labels)}

    # Load audio
    waveform, sample_rate = torchaudio.load(str(audio_path))
    if sample_rate != SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, sample_rate, SAMPLE_RATE)

    # Get emissions
    with torch.inference_mode():
        emissions, _ = model(waveform.to(device))
        emissions = torch.log_softmax(emissions, dim=-1).cpu()

    emission = emissions[0]
    tokens = _text_to_tokens(transcript, dictionary)

    # CTC forced alignment
    trellis = _get_trellis(emission, tokens, _get_blank_id(dictionary))
    path = _backtrack(trellis, emission, tokens, _get_blank_id(dictionary))
    char_segments = _merge_repeats(path, transcript.replace(" ", "|"))

    # Convert to words
    duration = waveform.shape[1] / SAMPLE_RATE
    ratio = duration / (trellis.shape[0] - 1)

    return _segments_to_words(char_segments, ratio)


def _get_blank_id(dictionary: dict[str, int]) -> int:
    for char, code in dictionary.items():
        if char in ("[pad]", "<pad>"):
            return code
    return 0


def _text_to_tokens(text: str, dictionary: dict[str, int]) -> list[int]:
    text = text.lower().replace(" ", "|")
    return [dictionary.get(c, 0) for c in text if c in dictionary or c == "|"]


def _get_trellis(emission: torch.Tensor, tokens: list[int], blank_id: int) -> torch.Tensor:
    import torch  # noqa: PLC0415

    num_frames, num_tokens = emission.shape[0], len(tokens)
    trellis = torch.zeros((num_frames, num_tokens))
    trellis[1:, 0] = torch.cumsum(emission[1:, blank_id], 0)
    trellis[0, 1:] = -float("inf")
    trellis[-num_tokens + 1 :, 0] = float("inf")

    for t in range(num_frames - 1):
        trellis[t + 1, 1:] = torch.maximum(
            trellis[t, 1:] + emission[t, blank_id],
            trellis[t, :-1] + emission[t, [tokens[i] for i in range(1, len(tokens))]],
        )
    return trellis


def _backtrack(
    trellis: torch.Tensor,
    emission: torch.Tensor,
    tokens: list[int],
    blank_id: int,
) -> list[tuple[int, int, float]]:
    """Returns list of (token_idx, time_idx, score)."""
    t, j = trellis.shape[0] - 1, trellis.shape[1] - 1
    path = [(j, t, emission[t, blank_id].exp().item())]

    while j > 0 and t > 0:
        stayed = trellis[t - 1, j] + emission[t - 1, blank_id]
        changed = trellis[t - 1, j - 1] + emission[t - 1, tokens[j]]

        t -= 1
        if changed > stayed:
            j -= 1
            score = emission[t, tokens[j + 1]].exp().item()
        else:
            score = emission[t, blank_id].exp().item()
        path.append((j, t, score))

    while t > 0:
        t -= 1
        path.append((0, t, emission[t, blank_id].exp().item()))

    return path[::-1]


def _merge_repeats(
    path: list[tuple[int, int, float]],
    transcript: str,
) -> list[tuple[str, int, int, float]]:
    """Merge repeated tokens into segments. Returns (char, start, end, score)."""
    segments = []
    i = 0
    while i < len(path):
        j = i
        while j < len(path) and path[i][0] == path[j][0]:
            j += 1
        token_idx = path[i][0]
        if token_idx < len(transcript):
            char = transcript[token_idx]
            start = path[i][1]
            end = path[j - 1][1] + 1
            score = sum(p[2] for p in path[i:j]) / (j - i)
            segments.append((char, start, end, score))
        i = j
    return segments


def _segments_to_words(
    segments: list[tuple[str, int, int, float]],
    ratio: float,
) -> list[AlignedWord]:
    """Convert character segments to words (split on |)."""
    words = []
    current_word = ""
    word_start = None

    for char, start, end, _ in segments:
        if char == "|":
            if current_word and word_start is not None:
                words.append(AlignedWord(current_word, word_start * ratio, end * ratio))
            current_word = ""
            word_start = None
        else:
            if word_start is None:
                word_start = start
            current_word += char
            word_end = end

    if current_word and word_start is not None:
        words.append(AlignedWord(current_word, word_start * ratio, word_end * ratio))

    return words
