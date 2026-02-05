"""Tests for alignment helpers."""

from __future__ import annotations

from agent_cli.core.alignment import (
    _build_alignment_tokens,
    _segments_to_words,
)


def _mock_dictionary() -> dict[str, int]:
    chars = ["h", "e", "l", "o", "w", "r", "d", "|"]
    return {char: idx for idx, char in enumerate(chars)}


def test_build_alignment_tokens_skips_punctuation() -> None:
    dictionary = _mock_dictionary()
    words = ["Hello,", "world!"]

    tokens, token_to_word = _build_alignment_tokens(words, dictionary)

    assert len(tokens) == 11  # 5 letters + separator + 5 letters
    assert token_to_word.count(0) == 5
    assert token_to_word.count(1) == 5
    assert token_to_word.count(None) == 1


def test_segments_to_words_preserves_original_words() -> None:
    dictionary = _mock_dictionary()
    words = ["Hello,", "world!"]
    tokens, token_to_word = _build_alignment_tokens(words, dictionary)

    segments = [(idx, idx * 2, idx * 2 + 1, 1.0) for idx in range(len(tokens))]
    aligned = _segments_to_words(segments, token_to_word, words, ratio=0.5)

    assert [word.word for word in aligned] == words
    assert aligned[0].start == 0.0
    assert aligned[1].start > aligned[0].end


def test_segments_to_words_fills_missing_bounds() -> None:
    dictionary = _mock_dictionary()
    words = ["---", "Hi"]
    _tokens, token_to_word = _build_alignment_tokens(words, dictionary)

    segments = [(0, 10, 12, 1.0), (1, 12, 14, 1.0)]
    aligned = _segments_to_words(segments, token_to_word, words, ratio=0.5)

    assert [word.word for word in aligned] == words
    assert aligned[0].start == aligned[1].start
