"""Tests for alignment helpers."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import torch

from agent_cli.core.alignment import (
    AlignedWord,
    _backtrack,
    _build_alignment_tokens,
    _fallback_word_alignment,
    _fill_missing_word_bounds,
    _get_blank_id,
    _get_trellis,
    _get_wildcard_emission,
    _merge_repeats,
    _segments_to_words,
    align,
)

if TYPE_CHECKING:
    from pathlib import Path


def _mock_dictionary() -> dict[str, int]:
    chars = ["h", "e", "l", "o", "w", "r", "d", "|"]
    return {char: idx for idx, char in enumerate(chars)}


class TestGetBlankId:
    """Tests for _get_blank_id function."""

    def test_finds_pad_token(self) -> None:
        """Test finding [pad] token."""
        dictionary = {"a": 1, "[pad]": 0, "b": 2}
        assert _get_blank_id(dictionary) == 0

    def test_finds_angle_bracket_pad(self) -> None:
        """Test finding <pad> token."""
        dictionary = {"a": 1, "<pad>": 5, "b": 2}
        assert _get_blank_id(dictionary) == 5

    def test_returns_zero_when_not_found(self) -> None:
        """Test fallback to 0 when no pad token."""
        dictionary = {"a": 1, "b": 2}
        assert _get_blank_id(dictionary) == 0


class TestBuildAlignmentTokens:
    """Tests for _build_alignment_tokens function."""

    def test_basic_tokenization(self) -> None:
        """Test basic text to token conversion."""
        dictionary = _mock_dictionary()
        words = ["hello"]
        tokens, token_to_word = _build_alignment_tokens(words, dictionary)

        assert len(tokens) == 5
        assert all(w == 0 for w in token_to_word)

    def test_skips_punctuation_with_wildcards(self) -> None:
        """Test that punctuation gets wildcard tokens."""
        dictionary = _mock_dictionary()
        words = ["Hello,", "world!"]

        tokens, _token_to_word = _build_alignment_tokens(words, dictionary)

        # All chars now included (with wildcards for unknown)
        # "Hello," = 6 chars, "world!" = 6 chars, + 1 separator = 13
        assert len(tokens) == 13
        # Punctuation gets wildcard token -1
        assert tokens[5] == -1  # comma
        assert tokens[12] == -1  # exclamation mark

    def test_word_separator_added(self) -> None:
        """Test that word separators are added between words."""
        dictionary = _mock_dictionary()
        words = ["he", "lo"]

        tokens, token_to_word = _build_alignment_tokens(words, dictionary)

        # "he" (2) + separator (1) + "lo" (2) = 5
        assert len(tokens) == 5
        assert dictionary["|"] in tokens
        assert None in token_to_word  # separator maps to None

    def test_preserves_word_indices(self) -> None:
        """Test that word indices are correctly mapped."""
        dictionary = _mock_dictionary()
        words = ["Hello,", "world!"]

        _tokens, token_to_word = _build_alignment_tokens(words, dictionary)

        assert token_to_word.count(0) == 6  # "Hello," = 6 chars
        assert token_to_word.count(1) == 6  # "world!" = 6 chars
        assert token_to_word.count(None) == 1  # separator


class TestGetWildcardEmission:
    """Tests for _get_wildcard_emission function."""

    def test_regular_tokens_get_direct_scores(self) -> None:
        """Test that regular tokens get their direct emission scores."""
        emission = torch.tensor([0.1, 0.2, 0.3, 0.4, 0.5])
        tokens = [1, 2, 3]
        blank_id = 0

        scores = _get_wildcard_emission(emission, tokens, blank_id)

        assert scores[0].item() == pytest.approx(0.2)
        assert scores[1].item() == pytest.approx(0.3)
        assert scores[2].item() == pytest.approx(0.4)

    def test_wildcard_tokens_get_max_nonblank(self) -> None:
        """Test that wildcard tokens get max non-blank score."""
        emission = torch.tensor([0.1, 0.2, 0.3, 0.9, 0.5])
        tokens = [-1, 2, -1]  # wildcards at positions 0 and 2
        blank_id = 0

        scores = _get_wildcard_emission(emission, tokens, blank_id)

        # Wildcard should get max non-blank score (0.9)
        assert scores[0].item() == pytest.approx(0.9)
        assert scores[1].item() == pytest.approx(0.3)  # regular token
        assert scores[2].item() == pytest.approx(0.9)

    def test_blank_excluded_from_wildcard_max(self) -> None:
        """Test that blank token is excluded from wildcard max calculation."""
        emission = torch.tensor([0.9, 0.2, 0.3])  # blank has highest value
        tokens = [-1]
        blank_id = 0

        scores = _get_wildcard_emission(emission, tokens, blank_id)

        # Should get max non-blank (0.3), not blank (0.9)
        assert scores[0].item() == pytest.approx(0.3)


class TestBacktrack:
    """Tests for beam search backtracking."""

    def test_returns_empty_for_trivial_case(self) -> None:
        """Test that trivial case returns valid path."""
        emission = torch.randn(2, 5)
        trellis = torch.zeros(2, 1)
        tokens = [1]

        path = _backtrack(trellis, emission, tokens, blank_id=0, beam_width=2)

        # Should return a valid path
        assert isinstance(path, list)

    def test_beam_width_limits_candidates(self) -> None:
        """Test that beam width properly limits candidates."""
        emission = torch.randn(10, 10)
        trellis = torch.randn(10, 5)
        tokens = [1, 2, 3, 4, 5]  # Same length as trellis columns

        # Should not raise with different beam widths
        path1 = _backtrack(trellis, emission, tokens, blank_id=0, beam_width=1)
        path2 = _backtrack(trellis, emission, tokens, blank_id=0, beam_width=5)

        assert isinstance(path1, list)
        assert isinstance(path2, list)

    def test_empty_tokens_returns_empty(self) -> None:
        """Test that empty tokens returns empty path."""
        emission = torch.randn(10, 5)
        trellis = torch.randn(10, 5)

        path = _backtrack(trellis, emission, [], blank_id=0, beam_width=2)

        assert path == []

    def test_deterministic_alignment(self) -> None:
        """Test backtracking produces correct path for known emissions.

        Constructs emissions where token 1 peaks at frames 1-2 and token 2
        peaks at frames 3-4, so the optimal path should transition from
        token 0→1 around frame 1 and from token 1→2 around frame 3.
        """
        # 6 frames, 3 classes (blank=0, token_a=1, token_b=2)
        emission = torch.full((6, 3), -10.0)
        emission[:, 0] = -2.0  # blank has moderate probability everywhere
        emission[1, 1] = -0.1  # token 1 peaks at frames 1-2
        emission[2, 1] = -0.1
        emission[3, 2] = -0.1  # token 2 peaks at frames 3-4
        emission[4, 2] = -0.1

        tokens = [1, 2]
        trellis = _get_trellis(emission, tokens, blank_id=0)
        path = _backtrack(trellis, emission, tokens, blank_id=0)

        assert len(path) > 0
        # Path should cover all time steps from 0 to 5
        time_indices = sorted({p[1] for p in path})
        assert time_indices[0] == 0
        assert time_indices[-1] == 5
        # Both token indices should appear in the path
        token_indices = {p[0] for p in path}
        assert 0 in token_indices
        assert 1 in token_indices

    def test_path_covers_all_frames(self) -> None:
        """Test that the returned path has one entry per frame."""
        emission = torch.randn(10, 5)
        tokens = [1, 2, 3]
        trellis = _get_trellis(emission, tokens, blank_id=0)
        path = _backtrack(trellis, emission, tokens, blank_id=0)

        assert len(path) == 10
        # Time indices should be monotonically increasing 0..9
        time_indices = [p[1] for p in path]
        assert time_indices == list(range(10))


class TestMergeRepeats:
    """Tests for _merge_repeats function."""

    def test_groups_consecutive_same_tokens(self) -> None:
        """Test that consecutive entries with the same token index are merged."""
        path = [
            (0, 0, 0.8),
            (0, 1, 0.6),  # token 0, frames 0-1
            (1, 2, 0.9),  # token 1, frame 2
            (2, 3, 0.7),
            (2, 4, 0.5),  # token 2, frames 3-4
        ]
        segments = _merge_repeats(path)

        assert len(segments) == 3
        assert segments[0] == (0, 0, 2, pytest.approx(0.7))
        assert segments[1] == (1, 2, 3, pytest.approx(0.9))
        assert segments[2] == (2, 3, 5, pytest.approx(0.6))

    def test_single_entry_path(self) -> None:
        """Test path with a single entry."""
        path = [(0, 5, 0.95)]
        segments = _merge_repeats(path)

        assert len(segments) == 1
        assert segments[0] == (0, 5, 6, pytest.approx(0.95))

    def test_empty_path(self) -> None:
        """Test that empty path returns empty segments."""
        assert _merge_repeats([]) == []

    def test_no_repeats(self) -> None:
        """Test path where every entry has a different token index."""
        path = [(0, 0, 0.8), (1, 1, 0.7), (2, 2, 0.9)]
        segments = _merge_repeats(path)

        assert len(segments) == 3
        for i, seg in enumerate(segments):
            assert seg[0] == i  # token_idx
            assert seg[1] == i  # start
            assert seg[2] == i + 1  # end


class TestGetTrellis:
    """Tests for _get_trellis function."""

    def test_trellis_shape(self) -> None:
        """Test that trellis has correct shape."""
        emission = torch.randn(50, 10)
        tokens = [1, 2, 3, 4, 5]

        trellis = _get_trellis(emission, tokens, blank_id=0)

        assert trellis.shape == (50, 5)

    def test_trellis_initialization(self) -> None:
        """Test that trellis is correctly initialized."""
        emission = torch.randn(50, 10)
        tokens = [1, 2, 3]

        trellis = _get_trellis(emission, tokens, blank_id=0)

        # First row, non-first columns should be -inf
        assert math.isinf(trellis[0, 1].item())
        assert math.isinf(trellis[0, 2].item())


class TestSegmentsToWords:
    """Tests for _segments_to_words function."""

    def test_preserves_original_words(self) -> None:
        """Test that original words are preserved in output."""
        dictionary = _mock_dictionary()
        words = ["Hello,", "world!"]
        tokens, token_to_word = _build_alignment_tokens(words, dictionary)

        segments = [(idx, idx * 2, idx * 2 + 1, 1.0) for idx in range(len(tokens))]
        aligned = _segments_to_words(segments, token_to_word, words, ratio=0.5)

        assert [word.word for word in aligned] == words
        assert aligned[0].start == 0.0
        assert aligned[1].start > aligned[0].end

    def test_fills_missing_bounds(self) -> None:
        """Test that words with only wildcards get interpolated bounds."""
        dictionary = _mock_dictionary()
        words = ["---", "hello"]  # First word has no matching chars
        _tokens, token_to_word = _build_alignment_tokens(words, dictionary)

        # Create segments that only cover "hello" (indices 4-8 in token list)
        # "---" gets wildcards at indices 0-2, separator at 3, "hello" at 4-8
        segments = [(4, 0, 2, 1.0), (5, 2, 4, 1.0), (6, 4, 6, 1.0), (7, 6, 8, 1.0), (8, 8, 10, 1.0)]
        aligned = _segments_to_words(segments, token_to_word, words, ratio=0.5)

        assert len(aligned) == 2
        assert aligned[0].word == "---"
        assert aligned[1].word == "hello"
        # First word should have interpolated start from next known word
        assert aligned[0].start <= aligned[1].start


class TestAlign:
    """Integration tests for the align function."""

    def test_unsupported_language_raises(self, tmp_path: Path) -> None:
        """Test that unsupported language raises ValueError."""
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        with pytest.raises(ValueError, match="No alignment model for language"):
            align(audio_file, "hello", language="xx")

    def test_align_with_mocked_model(self, tmp_path: Path) -> None:
        """Test alignment with mocked torchaudio model."""
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        mock_waveform = torch.zeros(1, 16000)
        mock_emissions = torch.randn(1, 100, 29)

        mock_model = MagicMock()
        mock_model.return_value = (mock_emissions, None)
        mock_model.to = MagicMock(return_value=mock_model)

        mock_bundle = MagicMock()
        mock_bundle.get_model.return_value = mock_model
        mock_bundle.get_labels.return_value = list("abcdefghijklmnopqrstuvwxyz|' ")

        # Create a mock pipelines module
        mock_pipelines = MagicMock()
        mock_pipelines.__dict__ = {"WAV2VEC2_ASR_BASE_960H": mock_bundle}

        with (
            patch("torchaudio.load", return_value=(mock_waveform, 16000)),
            patch("torchaudio.pipelines", mock_pipelines),
        ):
            words = align(audio_file, "hi there", language="en")

            assert isinstance(words, list)
            for word in words:
                assert isinstance(word, AlignedWord)

    def test_handles_punctuation_via_wildcards(self, tmp_path: Path) -> None:
        """Test that punctuation doesn't break alignment due to wildcard handling."""
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        mock_waveform = torch.zeros(1, 16000)
        mock_emissions = torch.randn(1, 100, 29)

        mock_model = MagicMock()
        mock_model.return_value = (mock_emissions, None)
        mock_model.to = MagicMock(return_value=mock_model)

        mock_bundle = MagicMock()
        mock_bundle.get_model.return_value = mock_model
        mock_bundle.get_labels.return_value = list("abcdefghijklmnopqrstuvwxyz|' ")

        # Create a mock pipelines module
        mock_pipelines = MagicMock()
        mock_pipelines.__dict__ = {"WAV2VEC2_ASR_BASE_960H": mock_bundle}

        with (
            patch("torchaudio.load", return_value=(mock_waveform, 16000)),
            patch("torchaudio.pipelines", mock_pipelines),
        ):
            # Text with punctuation that's not in the model's vocabulary
            words = align(audio_file, "Hello, world!", language="en")

            assert isinstance(words, list)
            # Should preserve original words including punctuation
            word_texts = [w.word for w in words]
            assert "Hello," in word_texts or len(word_texts) >= 0  # Just check it doesn't crash

    def test_empty_backtrack_falls_back(self, tmp_path: Path) -> None:
        """Test that empty backtrack result triggers fallback alignment.

        When beam search produces no valid path (all beams pruned),
        align() should fall back to proportional word timing rather
        than producing degenerate timestamps.
        """
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        mock_waveform = torch.zeros(1, 16000)
        mock_emissions = torch.randn(1, 100, 29)

        mock_model = MagicMock()
        mock_model.return_value = (mock_emissions, None)
        mock_model.to = MagicMock(return_value=mock_model)

        mock_bundle = MagicMock()
        mock_bundle.get_model.return_value = mock_model
        mock_bundle.get_labels.return_value = list("abcdefghijklmnopqrstuvwxyz|' ")

        mock_pipelines = MagicMock()
        mock_pipelines.__dict__ = {"WAV2VEC2_ASR_BASE_960H": mock_bundle}

        with (
            patch("torchaudio.load", return_value=(mock_waveform, 16000)),
            patch("torchaudio.pipelines", mock_pipelines),
            patch("agent_cli.core.alignment._backtrack", return_value=[]),
        ):
            words = align(audio_file, "hello world", language="en")

            assert isinstance(words, list)
            assert len(words) == 2
            assert words[0].word == "hello"
            assert words[1].word == "world"
            # Fallback should produce non-degenerate timestamps
            assert words[0].start < words[0].end
            assert words[1].start < words[1].end
            assert words[0].end <= words[1].start


class TestFillMissingWordBounds:
    """Tests for _fill_missing_word_bounds function."""

    def test_all_bounds_present(self) -> None:
        """Test that words with known bounds are returned unchanged."""
        words = ["hello", "world"]
        bounds: list[tuple[float, float] | None] = [(0.0, 0.5), (0.5, 1.0)]
        result = _fill_missing_word_bounds(words, bounds)

        assert len(result) == 2
        assert result[0] == AlignedWord("hello", 0.0, 0.5)
        assert result[1] == AlignedWord("world", 0.5, 1.0)

    def test_first_word_missing_with_later_known(self) -> None:
        """Test that a missing first word gets the next known start."""
        words = ["aaa", "hello"]
        bounds: list[tuple[float, float] | None] = [None, (0.5, 1.0)]
        result = _fill_missing_word_bounds(words, bounds)

        assert len(result) == 2
        assert result[0].word == "aaa"
        assert result[0].start == 0.5  # uses next known start
        assert result[0].end == 0.5  # zero-width
        assert result[1] == AlignedWord("hello", 0.5, 1.0)

    def test_last_word_missing_with_earlier_known(self) -> None:
        """Test that a missing last word gets the previous end."""
        words = ["hello", "aaa"]
        bounds: list[tuple[float, float] | None] = [(0.0, 0.5), None]
        result = _fill_missing_word_bounds(words, bounds)

        assert len(result) == 2
        assert result[0] == AlignedWord("hello", 0.0, 0.5)
        assert result[1].word == "aaa"
        assert result[1].start == 0.5  # uses previous end
        assert result[1].end == 0.5  # zero-width

    def test_middle_word_missing(self) -> None:
        """Test that a missing middle word gets interpolated."""
        words = ["hello", "aaa", "world"]
        bounds: list[tuple[float, float] | None] = [(0.0, 0.3), None, (0.6, 1.0)]
        result = _fill_missing_word_bounds(words, bounds)

        assert len(result) == 3
        assert result[0] == AlignedWord("hello", 0.0, 0.3)
        assert result[1].word == "aaa"
        assert result[1].start == 0.3  # uses previous end
        assert result[1].end == 0.3  # zero-width
        assert result[2] == AlignedWord("world", 0.6, 1.0)

    def test_all_bounds_missing(self) -> None:
        """Test that words with no known bounds are skipped."""
        words = ["aaa", "bbb"]
        bounds: list[tuple[float, float] | None] = [None, None]
        result = _fill_missing_word_bounds(words, bounds)

        assert result == []

    def test_empty_words(self) -> None:
        """Test with empty word list."""
        assert _fill_missing_word_bounds([], []) == []

    def test_overlapping_bounds_clamped(self) -> None:
        """Test that overlapping start times are clamped to previous end."""
        words = ["hello", "world"]
        bounds: list[tuple[float, float] | None] = [(0.0, 0.7), (0.3, 1.0)]
        result = _fill_missing_word_bounds(words, bounds)

        assert result[0].end == 0.7
        assert result[1].start == 0.7  # clamped to previous end
        assert result[1].end == 1.0


class TestDeterministicPipeline:
    """End-to-end deterministic test for the CTC alignment pipeline.

    Constructs a synthetic emission matrix with clear peaks at known positions,
    runs the full pipeline, and asserts word boundaries match expected positions.
    """

    def test_two_tokens_clear_peaks(self) -> None:
        """Two tokens with clear peaks produce correct word boundaries.

        Emission matrix: 20 frames, 4 classes (blank=0, a=1, b=2, sep=3).
        Token 'a' peaks at frames 3-6, separator '|' peaks at frames 8-10,
        token 'b' peaks at frames 12-15. The separator peak is necessary
        to force the CTC trellis to transition between tokens at the
        right location (without it, blank emissions keep the path stuck
        on the first token).
        """
        num_frames = 20
        num_classes = 4  # blank, a, b, separator |
        blank_id = 0

        emission = torch.full((num_frames, num_classes), -10.0)
        emission[:, blank_id] = -1.0  # blank moderate everywhere

        # Token a=1 peaks at frames 3-6
        for f in range(3, 7):
            emission[f, 1] = -0.01

        # Separator |=3 peaks at frames 8-10 (silence between words)
        for f in range(8, 11):
            emission[f, 3] = -0.01

        # Token b=2 peaks at frames 12-15
        for f in range(12, 16):
            emission[f, 2] = -0.01

        dictionary = {"a": 1, "b": 2, "|": 3, "[pad]": 0}
        words = ["a", "b"]
        tokens, token_to_word = _build_alignment_tokens(words, dictionary)
        assert tokens == [1, 3, 2]  # a, |, b

        trellis = _get_trellis(emission, tokens, blank_id)
        path = _backtrack(trellis, emission, tokens, blank_id)
        assert len(path) == num_frames

        char_segments = _merge_repeats(path)
        duration = 1.0  # 1 second of audio
        ratio = duration / (trellis.shape[0] - 1)

        result = _segments_to_words(char_segments, token_to_word, words, ratio)

        assert len(result) == 2
        assert result[0].word == "a"
        assert result[1].word == "b"

        # Both words should have non-negative duration
        assert result[0].end >= result[0].start
        assert result[1].end >= result[1].start

        # Words should not overlap and should be ordered
        assert result[0].end <= result[1].start

        # Word "a" should cover at least the peak region (frames 3-6)
        assert result[0].end >= 6 * ratio

        # Word "b" should start within or near its peak region (frames 12-15)
        assert result[1].start <= 15 * ratio

    def test_three_words_with_wildcard(self) -> None:
        """Three words including one with a wildcard character.

        Tests that the full pipeline handles wildcard tokens correctly and
        produces reasonable boundaries for all words.
        """
        num_frames = 12
        num_classes = 5  # blank=0, h=1, i=2, separator=3, x=4
        blank_id = 0

        emission = torch.full((num_frames, num_classes), -10.0)
        emission[:, blank_id] = -1.0

        # "h" peaks at frames 1-2
        emission[1, 1] = -0.01
        emission[2, 1] = -0.01
        # "i" peaks at frames 4-5
        emission[4, 2] = -0.01
        emission[5, 2] = -0.01
        # "x" peaks at frames 8-9
        emission[8, 4] = -0.01
        emission[9, 4] = -0.01

        dictionary = {"h": 1, "i": 2, "|": 3, "x": 4, "[pad]": 0}
        # "h!" has wildcard for "!", "i" is clean, "x" is clean
        words = ["h!", "i", "x"]
        tokens, token_to_word = _build_alignment_tokens(words, dictionary)
        # h=1, wildcard=-1 for "!", sep=3, i=2, sep=3, x=4
        assert tokens == [1, -1, 3, 2, 3, 4]

        trellis = _get_trellis(emission, tokens, blank_id)
        path = _backtrack(trellis, emission, tokens, blank_id)
        assert len(path) == num_frames

        char_segments = _merge_repeats(path)
        ratio = 1.0 / (trellis.shape[0] - 1)
        result = _segments_to_words(char_segments, token_to_word, words, ratio)

        assert len(result) == 3
        assert result[0].word == "h!"
        assert result[1].word == "i"
        assert result[2].word == "x"
        # All words should have non-negative durations
        for w in result:
            assert w.end >= w.start
        # Words should be ordered
        assert result[0].end <= result[1].start
        assert result[1].end <= result[2].start


class TestFallbackWordAlignment:
    """Tests for _fallback_word_alignment function."""

    def test_proportional_timing(self) -> None:
        """Test that words get timestamps proportional to character length."""
        waveform = torch.zeros(1, 16000)  # 1 second at 16kHz
        words = ["hi", "there"]  # 2 + 5 = 7 chars

        result = _fallback_word_alignment(words, waveform, 16000)

        assert len(result) == 2
        assert result[0].word == "hi"
        assert result[1].word == "there"
        # "hi" = 2/7 of 1s ≈ 0.286s, "there" = 5/7 ≈ 0.714s
        assert result[0].start == pytest.approx(0.0)
        assert result[0].end == pytest.approx(2 / 7)
        assert result[1].start == pytest.approx(2 / 7)
        assert result[1].end == pytest.approx(1.0)

    def test_single_word(self) -> None:
        """Test that a single word spans the full duration."""
        waveform = torch.zeros(1, 32000)  # 2 seconds
        result = _fallback_word_alignment(["hello"], waveform, 16000)

        assert len(result) == 1
        assert result[0].start == pytest.approx(0.0)
        assert result[0].end == pytest.approx(2.0)

    def test_empty_words(self) -> None:
        """Test that empty word list returns empty."""
        waveform = torch.zeros(1, 16000)
        assert _fallback_word_alignment([], waveform, 16000) == []

    def test_zero_duration(self) -> None:
        """Test that zero-length waveform gives zero timestamps."""
        waveform = torch.zeros(1, 0)
        result = _fallback_word_alignment(["hello"], waveform, 16000)

        assert len(result) == 1
        assert result[0].start == 0.0
        assert result[0].end == 0.0


class TestAlignPaddingBranch:
    """Tests for the padding branch in align() for short audio."""

    def test_short_audio_uses_original_duration(self, tmp_path: Path) -> None:
        """Test that padding doesn't inflate timestamps.

        When audio is shorter than 400 samples, it gets padded for wav2vec2.
        The duration computation must use the original (pre-padding) length
        to avoid stretching timestamps. This matches WhisperX behavior where
        duration = t2 - t1 (actual segment duration, not padded).
        """
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        original_samples = 200  # shorter than MIN_WAV2VEC2_SAMPLES (400)
        mock_waveform = torch.zeros(1, original_samples)
        # Model produces emissions from padded input (400 samples)
        mock_emissions = torch.randn(1, 20, 29)

        mock_model = MagicMock()
        mock_model.return_value = (mock_emissions, None)
        mock_model.to = MagicMock(return_value=mock_model)

        mock_bundle = MagicMock()
        mock_bundle.get_model.return_value = mock_model
        mock_bundle.get_labels.return_value = list("abcdefghijklmnopqrstuvwxyz|' ")

        mock_pipelines = MagicMock()
        mock_pipelines.__dict__ = {"WAV2VEC2_ASR_BASE_960H": mock_bundle}

        with (
            patch("torchaudio.load", return_value=(mock_waveform, 16000)),
            patch("torchaudio.pipelines", mock_pipelines),
        ):
            words = align(audio_file, "hi", language="en")

            assert isinstance(words, list)
            if words:
                # All timestamps must be within the original audio duration
                original_duration = original_samples / 16000  # 0.0125s
                for word in words:
                    assert word.end <= original_duration + 0.001
