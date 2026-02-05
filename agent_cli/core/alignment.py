"""Forced alignment using wav2vec2 for word-level timestamps.

Based on whisperx's alignment approach with beam search backtracking.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import torch

SAMPLE_RATE = 16000
DEFAULT_BEAM_WIDTH = 2
MIN_WAV2VEC2_SAMPLES = 400

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

    # Handle minimum input length for wav2vec2 models
    lengths = None
    if waveform.shape[-1] < MIN_WAV2VEC2_SAMPLES:
        lengths = torch.as_tensor([waveform.shape[-1]]).to(device)
        waveform = torch.nn.functional.pad(
            waveform,
            (0, MIN_WAV2VEC2_SAMPLES - waveform.shape[-1]),
        )

    # Get emissions
    with torch.inference_mode():
        emissions, _ = model(waveform.to(device), lengths=lengths)
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
    """Build token sequence for alignment with wildcard support.

    Characters not in dictionary get token -1 (wildcard).
    This allows alignment to proceed even with unknown characters.
    """
    tokens: list[int] = []
    token_to_word: list[int | None] = []
    word_separator = dictionary.get("|")

    for index, word in enumerate(words):
        for char in word:
            char_lower = char.lower()
            if char_lower in dictionary:
                tokens.append(dictionary[char_lower])
            else:
                # Use wildcard (-1) for unknown characters
                tokens.append(-1)
            token_to_word.append(index)
        if word_separator is not None and index < len(words) - 1:
            tokens.append(word_separator)
            token_to_word.append(None)

    return tokens, token_to_word


def _get_wildcard_emission(
    frame_emission: torch.Tensor,
    tokens: list[int],
    blank_id: int,
) -> torch.Tensor:
    """Get emission scores, using max non-blank for wildcard tokens (-1).

    Wildcards are used for characters not in the model's dictionary.
    For these, we use the maximum probability across all non-blank tokens.
    """
    import torch  # noqa: PLC0415

    tokens_tensor = torch.tensor(tokens) if not isinstance(tokens, torch.Tensor) else tokens
    wildcard_mask = tokens_tensor == -1

    # Get scores for non-wildcard positions (clamp to avoid -1 index)
    regular_scores = frame_emission[tokens_tensor.clamp(min=0).long()]

    # For wildcards, use max non-blank score
    max_valid_score = frame_emission.clone()
    max_valid_score[blank_id] = float("-inf")
    max_valid_score = max_valid_score.max()

    return torch.where(wildcard_mask, max_valid_score, regular_scores)


def _get_trellis(emission: torch.Tensor, tokens: list[int], blank_id: int) -> torch.Tensor:
    """Build CTC trellis with wildcard support for unknown characters."""
    import torch  # noqa: PLC0415

    num_frames, num_tokens = emission.shape[0], len(tokens)
    trellis = torch.zeros((num_frames, num_tokens))
    trellis[1:, 0] = torch.cumsum(emission[1:, blank_id], 0)
    trellis[0, 1:] = -float("inf")
    trellis[-num_tokens + 1 :, 0] = float("inf")

    for t in range(num_frames - 1):
        # Use wildcard emission for proper handling of unknown characters
        token_emissions = _get_wildcard_emission(emission[t], tokens[1:], blank_id)
        trellis[t + 1, 1:] = torch.maximum(
            trellis[t, 1:] + emission[t, blank_id],
            trellis[t, :-1] + token_emissions,
        )
    return trellis


@dataclass
class _BeamState:
    """State for beam search backtracking."""

    token_index: int
    time_index: int
    score: float
    path: list[tuple[int, int, float]]


def _backtrack(
    trellis: torch.Tensor,
    emission: torch.Tensor,
    tokens: list[int],
    blank_id: int,
    beam_width: int = DEFAULT_BEAM_WIDTH,
) -> list[tuple[int, int, float]]:
    """Beam search backtracking for more robust CTC alignment.

    Based on WhisperX's backtrack_beam implementation.
    Returns list of (token_idx, time_idx, score).
    """
    if not tokens or trellis.shape[1] == 0:
        return []

    t, j = trellis.shape[0] - 1, trellis.shape[1] - 1

    init_state = _BeamState(
        token_index=j,
        time_index=t,
        score=float(trellis[t, j]),
        path=[(j, t, emission[t, blank_id].exp().item())],
    )

    beams = [init_state]

    while beams and beams[0].token_index > 0:
        next_beams: list[_BeamState] = []

        for beam in beams:
            t, j = beam.time_index, beam.token_index

            if t <= 0:
                continue

            p_stay = emission[t - 1, blank_id]
            p_change = _get_wildcard_emission(emission[t - 1], [tokens[j]], blank_id)[0]

            stay_score = float(trellis[t - 1, j])
            change_score = float(trellis[t - 1, j - 1]) if j > 0 else float("-inf")

            # Stay path
            if not math.isinf(stay_score):
                new_path = beam.path.copy()
                new_path.append((j, t - 1, p_stay.exp().item()))
                next_beams.append(
                    _BeamState(
                        token_index=j,
                        time_index=t - 1,
                        score=stay_score,
                        path=new_path,
                    ),
                )

            # Change path
            if j > 0 and not math.isinf(change_score):
                new_path = beam.path.copy()
                new_path.append((j - 1, t - 1, p_change.exp().item()))
                next_beams.append(
                    _BeamState(
                        token_index=j - 1,
                        time_index=t - 1,
                        score=change_score,
                        path=new_path,
                    ),
                )

        # Keep top beam_width paths by score
        beams = sorted(next_beams, key=lambda x: x.score, reverse=True)[:beam_width]

        if not beams:
            break

    if not beams:
        return []

    # Complete the best path
    best_beam = beams[0]
    t = best_beam.time_index
    j = best_beam.token_index
    while t > 0:
        prob = emission[t - 1, blank_id].exp().item()
        best_beam.path.append((j, t - 1, prob))
        t -= 1

    return best_beam.path[::-1]


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
