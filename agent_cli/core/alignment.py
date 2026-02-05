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
        sample_rate = SAMPLE_RATE

    # Get emissions
    with torch.inference_mode():
        emissions, _ = model(waveform.to(device))
        emissions = torch.log_softmax(emissions, dim=-1).cpu()

    emission = emissions[0]
    words = _split_words(transcript)
    if not words:
        return []
    tokens, token_to_word = _build_alignment_tokens(words, dictionary)
    if not tokens:
        return _fallback_word_alignment(words, waveform, sample_rate)

    # CTC forced alignment
    trellis = _get_trellis(emission, tokens, _get_blank_id(dictionary))
    path = _backtrack(trellis, emission, tokens, _get_blank_id(dictionary))
    char_segments = _merge_repeats(path)

    # Convert to words
    if trellis.shape[0] <= 1:
        return _fallback_word_alignment(words, waveform, sample_rate)

    duration = waveform.shape[1] / sample_rate
    ratio = duration / (trellis.shape[0] - 1)

    return _segments_to_words(char_segments, token_to_word, words, ratio)


def _get_blank_id(dictionary: dict[str, int]) -> int:
    for char, code in dictionary.items():
        if char in ("[pad]", "<pad>"):
            return code
    return 0


def _split_words(text: str) -> list[str]:
    return [word for word in text.split() if word]


def _build_alignment_tokens(
    words: list[str],
    dictionary: dict[str, int],
) -> tuple[list[int], list[int | None]]:
    tokens: list[int] = []
    token_to_word: list[int | None] = []
    word_separator = dictionary.get("|")

    for index, word in enumerate(words):
        for char in word:
            char_lower = char.lower()
            if char_lower in dictionary:
                tokens.append(dictionary[char_lower])
                token_to_word.append(index)
        if word_separator is not None and index < len(words) - 1:
            tokens.append(word_separator)
            token_to_word.append(None)

    return tokens, token_to_word


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
) -> list[tuple[int, int, int, float]]:
    """Merge repeated tokens into segments. Returns (token_idx, start, end, score)."""
    segments: list[tuple[int, int, int, float]] = []
    i = 0
    while i < len(path):
        j = i
        while j < len(path) and path[i][0] == path[j][0]:
            j += 1
        token_idx = path[i][0]
        start = path[i][1]
        end = path[j - 1][1] + 1
        score = sum(p[2] for p in path[i:j]) / (j - i)
        segments.append((token_idx, start, end, score))
        i = j
    return segments


def _segments_to_words(
    segments: list[tuple[int, int, int, float]],
    token_to_word: list[int | None],
    words: list[str],
    ratio: float,
) -> list[AlignedWord]:
    """Convert character segments to words using token->word mapping."""
    word_bounds: list[tuple[float, float] | None] = [None] * len(words)

    for token_idx, start, end, _ in segments:
        if token_idx >= len(token_to_word):
            continue
        word_index = token_to_word[token_idx]
        if word_index is None:
            continue
        start_time = start * ratio
        end_time = end * ratio
        existing = word_bounds[word_index]
        if existing is None:
            word_bounds[word_index] = (start_time, end_time)
        else:
            word_bounds[word_index] = (
                min(existing[0], start_time),
                max(existing[1], end_time),
            )

    return _fill_missing_word_bounds(words, word_bounds)


def _fill_missing_word_bounds(
    words: list[str],
    word_bounds: list[tuple[float, float] | None],
) -> list[AlignedWord]:
    if not words:
        return []

    next_known_start: list[float | None] = [None] * len(words)
    next_start: float | None = None
    for idx in range(len(words) - 1, -1, -1):
        bounds = word_bounds[idx]
        if bounds is not None:
            next_start = bounds[0]
        next_known_start[idx] = next_start

    result: list[AlignedWord] = []
    last_end: float | None = None
    for idx, word in enumerate(words):
        bounds = word_bounds[idx]
        if bounds is None:
            if last_end is None and next_known_start[idx] is None:
                continue
            start_time = next_known_start[idx] if last_end is None else last_end
            if start_time is None:
                continue
            end_time = start_time
        else:
            start_time, end_time = bounds
            if last_end is not None and start_time < last_end:
                start_time = last_end
                end_time = max(end_time, start_time)
        result.append(AlignedWord(word, start_time, end_time))
        last_end = result[-1].end

    return result


def _fallback_word_alignment(
    words: list[str],
    waveform: torch.Tensor,
    sample_rate: int,
) -> list[AlignedWord]:
    """Fallback to proportional timings when no alignable tokens are found."""
    if not words:
        return []

    total_duration = waveform.shape[1] / sample_rate if sample_rate else 0.0
    if total_duration <= 0:
        return [AlignedWord(word, 0.0, 0.0) for word in words]

    total_chars = sum(len(word) for word in words)
    if total_chars == 0:
        step = total_duration / len(words)
        current = 0.0
        aligned: list[AlignedWord] = []
        for word in words:
            aligned.append(AlignedWord(word, current, current + step))
            current += step
        return aligned

    current = 0.0
    aligned_words: list[AlignedWord] = []
    for word in words:
        word_chars = max(1, len(word))
        duration = (word_chars / total_chars) * total_duration
        aligned_words.append(AlignedWord(word, current, current + duration))
        current += duration

    return aligned_words
