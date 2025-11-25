"""Tests for RAG utilities."""

from pathlib import Path
from typing import Any

from agent_cli.rag import _utils


def test_chunk_text_simple() -> None:
    """Test simple text chunking."""
    text = "Hello world. This is a test."
    chunks = _utils.chunk_text(text, chunk_size=100, overlap=0)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_split() -> None:
    """Test chunking with splitting."""
    # Create a text with multiple sentences
    sentences = ["Sentence 1.", "Sentence 2.", "Sentence 3.", "Sentence 4."]
    text = " ".join(sentences)

    # Small chunk size to force split
    # "Sentence 1." is 11 chars.
    chunks = _utils.chunk_text(text, chunk_size=25, overlap=0)

    # Expecting roughly: ["Sentence 1. Sentence 2.", "Sentence 3. Sentence 4."]
    # But strict length might vary.
    assert len(chunks) >= 2
    assert "Sentence 1." in chunks[0]
    assert "Sentence 4." in chunks[-1]


def test_chunk_text_overlap() -> None:
    """Test chunking with overlap."""
    text = "A. B. C. D. E. F."
    # Chunk size small enough to fit maybe 2-3 sentences
    # Overlap enough to repeat 1
    chunks = _utils.chunk_text(text, chunk_size=6, overlap=3)

    # "A. B. " -> 6 chars
    # "C. D. " -> 6 chars
    # If overlap is used, we might see overlap.

    assert len(chunks) > 1  # Check for overlap if logic supports it strictly
    # For now just ensure no data loss
    reconstructed = "".join(chunks).replace(" ", "").replace(".", "")
    original = text.replace(" ", "").replace(".", "")
    # Reconstructed might be longer due to overlap
    assert len(reconstructed) >= len(original)


def test_load_document_text_txt(tmp_path: Path) -> None:
    """Test loading text file."""
    f = tmp_path / "test.txt"
    f.write_text("hello world", encoding="utf-8")

    content = _utils.load_document_text(f)
    assert content == "hello world"


def test_load_document_text_unsupported(tmp_path: Path) -> None:
    """Test loading unsupported file."""
    f = tmp_path / "test.xyz"
    f.write_text("content", encoding="utf-8")

    content = _utils.load_document_text(f)
    assert content is None


def test_load_document_text_markitdown(tmp_path: Path, mocker: Any) -> None:
    """Test loading document using MarkItDown (mocked)."""
    # Mock MarkItDown class
    mock_cls = mocker.patch("markitdown.MarkItDown")
    mock_instance = mock_cls.return_value
    mock_result = mock_instance.convert.return_value
    mock_result.text_content = "mocked content"

    # Create a dummy PDF file
    f = tmp_path / "test.pdf"
    f.touch()

    content = _utils.load_document_text(f)

    assert content == "mocked content"
    mock_cls.assert_called_once()
    mock_instance.convert.assert_called_once_with(str(f))


def test_chunk_text_hard_split_oversized() -> None:
    """Test chunking with oversized content (no sentence boundaries)."""
    # Simulate a code file with no sentence-ending punctuation
    code_like_text = "x = 1\ny = 2\nz = 3\n" * 100  # ~1200 chars, no periods

    chunks = _utils.chunk_text(code_like_text, chunk_size=200, overlap=50)

    # Should produce multiple chunks, none exceeding chunk_size
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 200, f"Chunk too large: {len(chunk)} chars"

    # Verify all content is covered (with some overlap duplication)
    total_unique = set("".join(chunks))
    assert total_unique >= set(code_like_text)


def test_hard_split_direct() -> None:
    """Test _hard_split function directly."""
    text = "A" * 500
    chunks = _utils._hard_split(text, chunk_size=100, overlap=20)

    # With 500 chars, chunk_size=100, overlap=20:
    # Chunk 1: 0-100 (100 chars), next start: 100-20=80
    # Chunk 2: 80-180 (100 chars), next start: 180-20=160
    # etc.
    assert len(chunks) >= 5
    for chunk in chunks:
        assert len(chunk) <= 100


def test_get_file_hash(tmp_path: Path) -> None:
    """Test file hashing."""
    f = tmp_path / "test.txt"
    f.write_text("content", encoding="utf-8")

    h1 = _utils.get_file_hash(f)

    f.write_text("content", encoding="utf-8")  # Same content
    h2 = _utils.get_file_hash(f)

    assert h1 == h2

    f.write_text("modified", encoding="utf-8")
    h3 = _utils.get_file_hash(f)

    assert h1 != h3
