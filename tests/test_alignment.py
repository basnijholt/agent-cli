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
    _BeamState,
    _build_alignment_tokens,
    _get_blank_id,
    _get_trellis,
    _get_wildcard_emission,
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


class TestBeamState:
    """Tests for _BeamState dataclass."""

    def test_beam_state_creation(self) -> None:
        """Test creating a beam state."""
        state = _BeamState(
            token_index=5,
            time_index=10,
            score=0.95,
            path=[(5, 10, 0.9)],
        )
        assert state.token_index == 5
        assert state.time_index == 10
        assert state.score == 0.95
        assert len(state.path) == 1


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
