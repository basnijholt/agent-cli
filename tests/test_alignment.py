"""Tests for the forced alignment module."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import torch

from agent_cli.core.alignment import (
    ALIGN_MODELS,
    AlignedWord,
    _get_blank_id,
    _merge_repeats,
    _segments_to_words,
    _text_to_tokens,
    align,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestAlignedWord:
    """Tests for the AlignedWord dataclass."""

    def test_create_aligned_word(self):
        """Test creating an aligned word."""
        word = AlignedWord(word="hello", start=0.5, end=1.2)
        assert word.word == "hello"
        assert word.start == 0.5
        assert word.end == 1.2


class TestAlignModels:
    """Tests for the alignment model configuration."""

    def test_supported_languages(self):
        """Test that expected languages are supported."""
        assert "en" in ALIGN_MODELS
        assert "fr" in ALIGN_MODELS
        assert "de" in ALIGN_MODELS
        assert "es" in ALIGN_MODELS
        assert "it" in ALIGN_MODELS

    def test_model_names(self):
        """Test that model names follow expected pattern."""
        assert ALIGN_MODELS["en"] == "WAV2VEC2_ASR_BASE_960H"
        assert "VOXPOPULI" in ALIGN_MODELS["fr"]


class TestGetBlankId:
    """Tests for the _get_blank_id function."""

    def test_finds_pad_token(self):
        """Test finding [pad] token."""
        dictionary = {"a": 1, "b": 2, "[pad]": 0, "c": 3}
        assert _get_blank_id(dictionary) == 0

    def test_finds_angle_bracket_pad(self):
        """Test finding <pad> token."""
        dictionary = {"a": 1, "<pad>": 5, "b": 2}
        assert _get_blank_id(dictionary) == 5

    def test_returns_zero_when_not_found(self):
        """Test fallback to 0 when no pad token."""
        dictionary = {"a": 1, "b": 2, "c": 3}
        assert _get_blank_id(dictionary) == 0


class TestTextToTokens:
    """Tests for the _text_to_tokens function."""

    def test_basic_conversion(self):
        """Test basic text to token conversion."""
        dictionary = {"h": 0, "e": 1, "l": 2, "o": 3, "|": 4}
        tokens = _text_to_tokens("hello", dictionary)
        assert tokens == [0, 1, 2, 2, 3]

    def test_spaces_become_pipes(self):
        """Test that spaces are converted to pipe symbols."""
        dictionary = {"h": 0, "i": 1, "|": 2, "t": 3, "e": 4, "r": 5}
        tokens = _text_to_tokens("hi there", dictionary)
        assert 2 in tokens  # pipe token should be present

    def test_unknown_chars_are_skipped(self):
        """Test that unknown characters are skipped."""
        dictionary = {"a": 1, "b": 2}
        tokens = _text_to_tokens("abc", dictionary)
        # 'c' is not in dictionary, should be skipped
        assert tokens == [1, 2]

    def test_case_insensitive(self):
        """Test that conversion is case-insensitive."""
        dictionary = {"h": 0, "e": 1, "l": 2, "o": 3}
        tokens = _text_to_tokens("HELLO", dictionary)
        assert tokens == [0, 1, 2, 2, 3]


class TestMergeRepeats:
    """Tests for the _merge_repeats function."""

    def test_merge_repeated_tokens(self):
        """Test merging repeated tokens."""
        # Path format: (token_idx, time_idx, score)
        path = [
            (0, 0, 0.9),
            (0, 1, 0.8),
            (1, 2, 0.7),
            (1, 3, 0.6),
            (1, 4, 0.5),
        ]
        transcript = "ab"
        segments = _merge_repeats(path, transcript)

        assert len(segments) == 2
        # First segment: char 'a', frames 0-1
        assert segments[0][0] == "a"
        assert segments[0][1] == 0  # start
        assert segments[0][2] == 2  # end (path[1][1] + 1)
        # Second segment: char 'b', frames 2-4
        assert segments[1][0] == "b"
        assert segments[1][1] == 2  # start
        assert segments[1][2] == 5  # end (path[4][1] + 1)

    def test_empty_path(self):
        """Test with empty path."""
        segments = _merge_repeats([], "abc")
        assert segments == []

    def test_single_token(self):
        """Test with single token."""
        path = [(0, 5, 0.9)]
        segments = _merge_repeats(path, "x")
        assert len(segments) == 1
        assert segments[0][0] == "x"


class TestSegmentsToWords:
    """Tests for the _segments_to_words function."""

    def test_basic_word_splitting(self):
        """Test splitting segments into words on pipe character."""
        segments = [
            ("h", 0, 1, 0.9),
            ("i", 1, 2, 0.9),
            ("|", 2, 3, 0.9),
            ("t", 3, 4, 0.9),
            ("h", 4, 5, 0.9),
            ("e", 5, 6, 0.9),
            ("r", 6, 7, 0.9),
            ("e", 7, 8, 0.9),
        ]
        ratio = 0.1  # 0.1 seconds per frame
        words = _segments_to_words(segments, ratio)

        assert len(words) == 2
        assert words[0].word == "hi"
        assert words[0].start == 0.0
        assert words[0].end == pytest.approx(0.3)  # end of pipe
        assert words[1].word == "there"
        assert words[1].start == pytest.approx(0.3)

    def test_single_word(self):
        """Test with single word (no pipes)."""
        segments = [
            ("h", 0, 1, 0.9),
            ("i", 1, 2, 0.9),
        ]
        ratio = 1.0
        words = _segments_to_words(segments, ratio)

        assert len(words) == 1
        assert words[0].word == "hi"
        assert words[0].start == 0.0
        assert words[0].end == 2.0

    def test_empty_segments(self):
        """Test with empty segments."""
        words = _segments_to_words([], 1.0)
        assert words == []

    def test_only_pipes(self):
        """Test with only pipe characters."""
        segments = [
            ("|", 0, 1, 0.9),
            ("|", 1, 2, 0.9),
        ]
        words = _segments_to_words(segments, 1.0)
        assert words == []


class TestAlign:
    """Tests for the main align function."""

    def test_unsupported_language_raises(self, tmp_path: Path):
        """Test that unsupported language raises ValueError."""
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        with pytest.raises(ValueError, match="No alignment model for language"):
            align(audio_file, "hello world", language="xx")

    def test_align_with_mocked_torchaudio(self, tmp_path: Path):
        """Test alignment with mocked torchaudio and model."""
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        # Mock waveform: 1 channel, 16000 samples (1 second at 16kHz)
        mock_waveform = torch.zeros(1, 16000)
        mock_sample_rate = 16000

        # Mock emissions: 100 frames, 29 tokens (typical for wav2vec2)
        mock_emissions = torch.randn(1, 100, 29)

        # Mock model that returns emissions tuple
        mock_model = MagicMock()
        mock_model.return_value = (mock_emissions, None)
        mock_model.to = MagicMock(return_value=mock_model)

        # Mock bundle
        mock_bundle = MagicMock()
        mock_bundle.get_model.return_value = mock_model
        mock_bundle.get_labels.return_value = list("abcdefghijklmnopqrstuvwxyz|' ")

        # Create mock torchaudio module
        mock_torchaudio = MagicMock()
        mock_torchaudio.load.return_value = (mock_waveform, mock_sample_rate)
        mock_torchaudio.pipelines.__dict__ = {"WAV2VEC2_ASR_BASE_960H": mock_bundle}

        with patch.dict(sys.modules, {"torchaudio": mock_torchaudio}):
            # Simple transcript
            words = align(audio_file, "hi", language="en")

            # Should return some words (exact result depends on CTC alignment)
            assert isinstance(words, list)
            for word in words:
                assert isinstance(word, AlignedWord)

    def test_align_resamples_if_needed(self, tmp_path: Path):
        """Test that audio is resampled if sample rate differs from 16kHz."""
        audio_file = tmp_path / "test.wav"
        audio_file.touch()

        # Mock waveform at 48kHz (needs resampling)
        mock_waveform = torch.zeros(1, 48000)  # 1 second at 48kHz
        mock_sample_rate = 48000

        mock_emissions = torch.randn(1, 100, 29)
        mock_model = MagicMock()
        mock_model.return_value = (mock_emissions, None)
        mock_model.to = MagicMock(return_value=mock_model)

        mock_bundle = MagicMock()
        mock_bundle.get_model.return_value = mock_model
        mock_bundle.get_labels.return_value = list("abcdefghijklmnopqrstuvwxyz|' ")

        # Create mock torchaudio module
        mock_torchaudio = MagicMock()
        mock_torchaudio.load.return_value = (mock_waveform, mock_sample_rate)
        mock_torchaudio.pipelines.__dict__ = {"WAV2VEC2_ASR_BASE_960H": mock_bundle}
        mock_torchaudio.functional.resample.return_value = torch.zeros(1, 16000)

        with patch.dict(sys.modules, {"torchaudio": mock_torchaudio}):
            align(audio_file, "hi", language="en")

            # Verify resample was called with correct parameters
            mock_torchaudio.functional.resample.assert_called_once()
            call_args = mock_torchaudio.functional.resample.call_args
            assert call_args[0][1] == 48000  # original sample rate
            assert call_args[0][2] == 16000  # target sample rate
